"""
Lantern v2 — Client Configuration
Настройки клиента, сохраняемые между сессиями.
"""

import json
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional


CONFIG_DIR = Path.home() / ".lantern_v2"
CONFIG_FILE = CONFIG_DIR / "client_config.json"
TOKENS_FILE = CONFIG_DIR / "auth_tokens.json"
EMOJI_CACHE_DIR = CONFIG_DIR / "emoji_cache"


@dataclass
class ThemeConfig:
    """Настройки темы."""
    palette: str = "mocha"
    accent_color: str = "mauve"
    animations_enabled: bool = True
    animation_speed: float = 1.0

    # Шрифты
    ui_font: str = "Inter"          # Семейство шрифта для интерфейса
    ui_font_size: int = 14          # Размер UI-шрифта
    code_font: str = "FiraCode"     # Семейство для блоков кода
    code_font_size: int = 13        # Размер code-шрифта


@dataclass
class NotificationConfig:
    """Настройки уведомлений."""
    enabled: bool = True
    sound_enabled: bool = True
    show_preview: bool = True  # Показывать текст в уведомлении
    do_not_disturb: bool = False


@dataclass
class ChatConfig:
    """Настройки чата."""
    font_size: int = 14
    message_grouping_seconds: int = 300  # Группировка сообщений от одного автора
    show_timestamps: bool = True
    enter_sends_message: bool = True  # Enter = отправить, Shift+Enter = новая строка
    show_typing_indicator: bool = True


@dataclass
class ClientConfig:
    """Полная конфигурация клиента Lantern v2."""

    # --- Подключение ---
    server_host: Optional[str] = None
    server_port: int = 8190
    auto_connect: bool = True
    use_zeroconf: bool = True

    # --- Профиль (кэш, основные данные на сервере) ---
    last_username: Optional[str] = None
    display_name: Optional[str] = None

    # --- Файлы ---
    download_path: str = str(Path.home() / "Downloads" / "Lantern")

    # --- Темы ---
    theme: ThemeConfig = field(default_factory=ThemeConfig)

    # --- Уведомления ---
    notifications: NotificationConfig = field(default_factory=NotificationConfig)

    # --- Чат ---
    chat: ChatConfig = field(default_factory=ChatConfig)

    # --- Стикеры ---
    sticker_packs_path: str = ""  # Путь к папкам со стикерами

    def save(self) -> None:
        """Сохраняет конфигурацию в JSON-файл."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls) -> "ClientConfig":
        """Загружает конфигурацию из файла или создаёт дефолтную."""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Восстанавливаем вложенные dataclass'ы
                if "theme" in data and isinstance(data["theme"], dict):
                    data["theme"] = ThemeConfig(**data["theme"])
                if "notifications" in data and isinstance(data["notifications"], dict):
                    data["notifications"] = NotificationConfig(**data["notifications"])
                if "chat" in data and isinstance(data["chat"], dict):
                    data["chat"] = ChatConfig(**data["chat"])

                return cls(**data)
            except (json.JSONDecodeError, TypeError, KeyError):
                # Если файл повреждён — создаём новый
                pass

        config = cls()
        config.save()
        return config


class AuthTokenStorage:
    """Хранилище JWT-токенов с привязкой к серверам."""

    def __init__(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._tokens: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        """Загружает токены из файла."""
        if TOKENS_FILE.exists():
            try:
                with open(TOKENS_FILE, "r", encoding="utf-8") as f:
                    self._tokens = json.load(f)
            except (json.JSONDecodeError, TypeError):
                self._tokens = {}

    def _save(self) -> None:
        """Сохраняет токены в файл."""
        with open(TOKENS_FILE, "w", encoding="utf-8") as f:
            json.dump(self._tokens, f, indent=2)

    def get_token(self, server_address: str) -> Optional[str]:
        """Получает токен для указанного сервера."""
        return self._tokens.get(server_address)

    def set_token(self, server_address: str, token: str) -> None:
        """Сохраняет токен для сервера."""
        self._tokens[server_address] = token
        self._save()

    def remove_token(self, server_address: str) -> None:
        """Удаляет токен для сервера."""
        self._tokens.pop(server_address, None)
        self._save()

    def clear(self) -> None:
        """Очищает все токены."""
        self._tokens.clear()
        self._save()
