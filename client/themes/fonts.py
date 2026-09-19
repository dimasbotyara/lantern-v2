"""
Lantern v2 — Bundled Fonts Loader
Загружает встроенные и кастомные шрифты из client/themes/fonts/
через QFontDatabase, чтобы приложение выглядело одинаково
на любой ОС (Linux, Windows, macOS, флешка).

Структура папки:
    client/themes/fonts/
    ├── Inter/               ← встроенный UI-шрифт
    ├── IBMPlexSans/         ← встроенный UI-шрифт
    ├── FiraCode/            ← встроенный Code-шрифт
    ├── JetBrainsMono/       ← встроенный Code-шрифт
    ├── NotoColorEmoji/      ← встроенный Emoji-шрифт
    └── мой_шрифт.ttf        ← кастомный шрифт от юзера
"""

from pathlib import Path
from typing import Optional

from PyQt5.QtGui import QFontDatabase


FONTS_DIR = Path(__file__).resolve().parent / "fonts"


# Метка категории у каждого шрифта: "ui", "code", "emoji", "custom"
# Заполняется при загрузке.
_loaded: dict[str, list[str]] = {
    "ui": [],
    "code": [],
    "emoji": [],
    "custom": [],
}


# Специальное: какие папки встроенных шрифтов к какой категории относятся.
# Всё что НЕ в этом словаре и лежит в корне — считается "custom".
BUILTIN_CATEGORIES: dict[str, str] = {
    "Inter": "ui",
    "IBMPlexSans": "ui",
    "FiraCode": "code",
    "JetBrainsMono": "code",
    "NotoColorEmoji": "emoji",
}


def load_all_fonts() -> dict[str, list[str]]:
    """
    Загружает все шрифты из FONTS_DIR (встроенные + кастомные).
    Возвращает маппинг {category: [font_family_names]}.

    Вызывать ПОСЛЕ QApplication(), но ДО создания MainWindow().
    """
    if any(_loaded.values()):
        return _loaded  # Уже загружено

    if not FONTS_DIR.exists():
        print(f"[Fonts] Папка {FONTS_DIR} не найдена")
        return _loaded

    # 1. Встроенные шрифты (папки в BUILTIN_CATEGORIES)
    for folder_name, category in BUILTIN_CATEGORIES.items():
        folder = FONTS_DIR / folder_name
        if not folder.exists():
            continue
        for ttf_file in sorted(folder.glob("*.ttf")):
            _load_font_file(ttf_file, category)

    # 2. Кастомные шрифты (файлы в корне FONTS_DIR)
    for ttf_file in sorted(FONTS_DIR.glob("*.ttf")):
        _load_font_file(ttf_file, "custom")
    for otf_file in sorted(FONTS_DIR.glob("*.otf")):
        _load_font_file(otf_file, "custom")

    return _loaded


def _load_font_file(font_path: Path, category: str) -> Optional[str]:
    """
    Загружает один .ttf/.otf файл через QFontDatabase.
    Возвращает имя семейства или None при ошибке.
    """
    font_id = QFontDatabase.addApplicationFont(str(font_path))
    if font_id < 0:
        print(f"[Fonts] ❌ Не удалось загрузить: {font_path.name}")
        return None

    families = QFontDatabase.applicationFontFamilies(font_id)
    if not families:
        print(f"[Fonts] ❌ Пустое семейство для: {font_path.name}")
        return None

    family = families[0]
    _loaded[category].append(family)
    print(f"[Fonts] ✅ {category}: {font_path.name} → {family}")
    return family


def _resolve_family(category: str, name: str) -> Optional[str]:
    """
    Находит реальное имя семейства в Qt по "логическому" имени.

    Qt использует ВНУТРЕННЕЕ имя шрифта из .ttf, а не имя файла.
    Например, файл FiraCode-Regular.ttf регистрируется как "Fira Code".

    Эта функция пытается найти соответствие:
    - Если name ТОЧНО есть в списке — вернуть его
    - Если name без пробелов совпадает с семейством без пробелов — вернуть
    - Если name содержится в семействе (без учёта пробелов и регистра) — вернуть
    """
    available = get_available_fonts(category)
    if not available:
        return None

    # Точное совпадение
    if name in available:
        return name

    # Совпадение без учёта пробелов и регистра
    normalized = name.lower().replace(" ", "").replace("-", "")
    for fam in available:
        fam_norm = fam.lower().replace(" ", "").replace("-", "")
        if fam_norm == normalized:
            return fam

    # Частичное совпадение (name — префикс или содержится)
    for fam in available:
        fam_norm = fam.lower().replace(" ", "").replace("-", "")
        if normalized in fam_norm or fam_norm in normalized:
            return fam

    return None


def get_available_fonts(category: str) -> list[str]:
    """
    Возвращает список доступных шрифтов для категории.
    Для UI и Code — встроенные + кастомные (встроенные первыми).
    """
    if category in ("ui", "code"):
        return _loaded[category] + _loaded["custom"]
    return _loaded.get(category, [])


def get_font_family(category: str = "ui", preferred: Optional[str] = None) -> str:
    """
    Возвращает имя семейства для использования в QFont/QSS.

    Args:
        category: "ui" | "code" | "emoji"
        preferred: имя из настроек (логическое, как в файле).
                   Может быть "FiraCode", а Qt ждёт "Fira Code" —
                   _resolve_family это разрулит.

    Returns:
        Реальное имя семейства в Qt или системный fallback.
    """
    if preferred:
        resolved = _resolve_family(category, preferred)
        if resolved:
            return resolved
        print(f"[Fonts] ⚠️  Шрифт '{preferred}' не найден, использую дефолт")

    # Дефолты
    defaults = {"ui": "Inter", "code": "FiraCode", "emoji": "NotoColorEmoji"}
    default_name = defaults.get(category, "sans-serif")

    resolved = _resolve_family(category, default_name)
    if resolved:
        return resolved

    # Совсем fallback
    if category == "code":
        return "monospace"
    return "sans-serif"


def get_font_css_stack(category: str = "ui", preferred: Optional[str] = None) -> str:
    """Возвращает CSS-стек для QSS."""
    primary = get_font_family(category, preferred)

    if category == "ui":
        return f'"{primary}", "Noto Sans", "DejaVu Sans", sans-serif'
    elif category == "code":
        return f'"{primary}", "Consolas", "Cascadia Code", monospace'
    elif category == "emoji":
        return f'"{primary}", "Segoe UI Emoji", "Apple Color Emoji", sans-serif'

    return f'"{primary}"'


def rescan_custom_fonts() -> list[str]:
    """
    Пересканировать папку на новые кастомные шрифты.
    Используется кнопкой "🔄 Обновить" в настройках.

    Возвращает список имён новых загруженных шрифтов.
    """
    before = set(_loaded["custom"])
    _loaded["custom"].clear()

    for ttf_file in sorted(FONTS_DIR.glob("*.ttf")):
        _load_font_file(ttf_file, "custom")
    for otf_file in sorted(FONTS_DIR.glob("*.otf")):
        _load_font_file(otf_file, "custom")

    after = set(_loaded["custom"])
    new_fonts = list(after - before)
    return new_fonts
