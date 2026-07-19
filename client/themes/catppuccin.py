"""
Lantern v2 — Catppuccin Color Palettes
Все 4 варианта палитры + 14 акцентных цветов.
Точные цвета из официальной спецификации catppuccin/catppuccin.

Каждая палитра содержит:
- Base colors (фоны, поверхности)
- Text colors (основной, второстепенный, приглушённый)
- Accent colors (14 штук на выбор)
- Overlay colors (для всплывающих элементов)
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AccentColor:
    """Акцентный цвет с именем."""
    name: str
    display_name: str
    hex: str

    @property
    def rgb(self) -> tuple[int, int, int]:
        h = self.hex.lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

    def with_alpha(self, alpha: int) -> str:
        """Возвращает rgba() строку."""
        r, g, b = self.rgb
        return f"rgba({r}, {g}, {b}, {alpha})"

    def dimmed(self, factor: float = 0.3) -> str:
        """Возвращает приглушённую версию цвета (для фонов)."""
        r, g, b = self.rgb
        return f"rgba({r}, {g}, {b}, {int(255 * factor)})"


@dataclass(frozen=True)
class Palette:
    """Полная цветовая палитра Catppuccin."""

    name: str
    display_name: str
    is_dark: bool

    # === Base ===
    crust: str       # Самый тёмный фон
    mantle: str      # Фон сайдбара
    base: str        # Основной фон
    surface0: str    # Поверхность 0 (поле ввода)
    surface1: str    # Поверхность 1 (hover)
    surface2: str    # Поверхность 2 (active)

    # === Overlay ===
    overlay0: str    # Оверлей 0 (disabled text)
    overlay1: str    # Оверлей 1 (placeholder)
    overlay2: str    # Оверлей 2 (иконки)

    # === Text ===
    text: str        # Основной текст
    subtext1: str    # Второстепенный текст
    subtext0: str    # Приглушённый текст

    # === Accent Colors ===
    rosewater: str
    flamingo: str
    pink: str
    mauve: str
    red: str
    maroon: str
    peach: str
    yellow: str
    green: str
    teal: str
    sky: str
    sapphire: str
    blue: str
    lavender: str

    def get_accent(self, name: str) -> AccentColor:
        """Получает акцентный цвет по имени."""
        color_hex = getattr(self, name, self.mauve)
        display_names = {
            "rosewater": "Розовая вода",
            "flamingo": "Фламинго",
            "pink": "Розовый",
            "mauve": "Сиреневый",
            "red": "Красный",
            "maroon": "Бордовый",
            "peach": "Персиковый",
            "yellow": "Жёлтый",
            "green": "Зелёный",
            "teal": "Бирюзовый",
            "sky": "Небесный",
            "sapphire": "Сапфировый",
            "blue": "Синий",
            "lavender": "Лавандовый",
        }
        return AccentColor(
            name=name,
            display_name=display_names.get(name, name),
            hex=color_hex,
        )

    def all_accents(self) -> list[AccentColor]:
        """Возвращает все 14 акцентных цветов."""
        names = [
            "rosewater", "flamingo", "pink", "mauve",
            "red", "maroon", "peach", "yellow",
            "green", "teal", "sky", "sapphire",
            "blue", "lavender",
        ]
        return [self.get_accent(n) for n in names]

    def nick_safe_colors(self, accent_name: str) -> list[str]:
        """
        Возвращает цвета для ников, которые НЕ конфликтуют с текущим акцентом.
        Убирает акцентный цвет и слишком похожие на него.
        """
        all_accent_names = [
            "rosewater", "flamingo", "pink", "mauve",
            "red", "maroon", "peach", "yellow",
            "green", "teal", "sky", "sapphire",
            "blue", "lavender",
        ]

        # Группы похожих цветов
        similar_groups = {
            "rosewater": {"flamingo"},
            "flamingo": {"rosewater"},
            "pink": {"mauve"},
            "mauve": {"pink", "lavender"},
            "red": {"maroon"},
            "maroon": {"red"},
            "peach": {"yellow"},
            "yellow": {"peach"},
            "green": {"teal"},
            "teal": {"green", "sky"},
            "sky": {"sapphire", "teal"},
            "sapphire": {"blue", "sky"},
            "blue": {"sapphire", "lavender"},
            "lavender": {"blue", "mauve"},
        }

        excluded = {accent_name}
        excluded.update(similar_groups.get(accent_name, set()))

        return [
            getattr(self, name)
            for name in all_accent_names
            if name not in excluded
        ]


# ========================
# Palette Definitions
# ========================

LATTE = Palette(
    name="latte",
    display_name="Latte ☀️",
    is_dark=False,

    crust="#dce0e8",
    mantle="#e6e9ef",
    base="#eff1f5",
    surface0="#ccd0da",
    surface1="#bcc0cc",
    surface2="#acb0be",

    overlay0="#9ca0b0",
    overlay1="#8c8fa1",
    overlay2="#7c7f93",

    text="#4c4f69",
    subtext1="#5c5f77",
    subtext0="#6c6f85",

    rosewater="#dc8a78",
    flamingo="#dd7878",
    pink="#ea76cb",
    mauve="#8839ef",
    red="#d20f39",
    maroon="#e64553",
    peach="#fe640b",
    yellow="#df8e1d",
    green="#40a02b",
    teal="#179299",
    sky="#04a5e5",
    sapphire="#209fb5",
    blue="#1e66f5",
    lavender="#7287fd",
)

FRAPPE = Palette(
    name="frappe",
    display_name="Frappé 🌙",
    is_dark=True,

    crust="#232634",
    mantle="#292c3c",
    base="#303446",
    surface0="#414559",
    surface1="#51576d",
    surface2="#626880",

    overlay0="#737994",
    overlay1="#838ba7",
    overlay2="#949cbb",

    text="#c6d0f5",
    subtext1="#b5bfe2",
    subtext0="#a5adce",

    rosewater="#f2d5cf",
    flamingo="#eebebe",
    pink="#f4b8e4",
    mauve="#ca9ee6",
    red="#e78284",
    maroon="#ea999c",
    peach="#ef9f76",
    yellow="#e5c890",
    green="#a6d189",
    teal="#81c8be",
    sky="#99d1db",
    sapphire="#85c1dc",
    blue="#8caaee",
    lavender="#babbf1",
)

MACCHIATO = Palette(
    name="macchiato",
    display_name="Macchiato 🌃",
    is_dark=True,

    crust="#181926",
    mantle="#1e2030",
    base="#24273a",
    surface0="#363a4f",
    surface1="#494d64",
    surface2="#5b6078",

    overlay0="#6e738d",
    overlay1="#8087a2",
    overlay2="#939ab7",

    text="#cad3f5",
    subtext1="#b8c0e0",
    subtext0="#a5adcb",

    rosewater="#f4dbd6",
    flamingo="#f0c6c6",
    pink="#f5bde6",
    mauve="#c6a0f6",
    red="#ed8796",
    maroon="#ee99a0",
    peach="#f5a97f",
    yellow="#eed49f",
    green="#a6da95",
    teal="#8bd5ca",
    sky="#91d7e3",
    sapphire="#7dc4e4",
    blue="#8aadf4",
    lavender="#b7bdf8",
)

MOCHA = Palette(
    name="mocha",
    display_name="Mocha 🌌",
    is_dark=True,

    crust="#11111b",
    mantle="#181825",
    base="#1e1e2e",
    surface0="#313244",
    surface1="#45475a",
    surface2="#585b70",

    overlay0="#6c7086",
    overlay1="#7f849c",
    overlay2="#9399b2",

    text="#cdd6f4",
    subtext1="#bac2de",
    subtext0="#a6adc8",

    rosewater="#f5e0dc",
    flamingo="#f2cdcd",
    pink="#f5c2e7",
    mauve="#cba6f7",
    red="#f38ba8",
    maroon="#eba0ac",
    peach="#fab387",
    yellow="#f9e2af",
    green="#a6e3a1",
    teal="#94e2d5",
    sky="#89dceb",
    sapphire="#74c7ec",
    blue="#89b4fa",
    lavender="#b4befe",
)

# Словарь всех палитр
PALETTES: dict[str, Palette] = {
    "latte": LATTE,
    "frappe": FRAPPE,
    "macchiato": MACCHIATO,
    "mocha": MOCHA,
}


def get_palette(name: str) -> Palette:
    """Получает палитру по имени. По умолчанию — Mocha."""
    return PALETTES.get(name, MOCHA)