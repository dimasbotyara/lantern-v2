"""
Lantern v2 — Server Configuration
Централизованная конфигурация сервера.
"""

from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field


class ServerConfig(BaseSettings):
    """Основные настройки сервера Lantern v2."""

    # --- Сеть ---
    host: str = Field(default="0.0.0.0", description="Адрес привязки сервера")
    port: int = Field(default=8190, description="Порт сервера")
    service_name: str = Field(default="Lantern v2 Chat", description="Имя сервиса для Zeroconf")

    # --- База данных ---
    database_url: str = Field(
        default="sqlite+aiosqlite:///./lantern_v2.db",
        description="URL подключения к БД"
    )

    # --- JWT ---
    jwt_secret_key: str = Field(
        default="lantern-v2-super-secret-key-change-me",
        description="Секретный ключ для подписи JWT-токенов"
    )
    jwt_algorithm: str = Field(default="HS256", description="Алгоритм JWT")
    jwt_expire_hours: int = Field(default=720, description="Время жизни токена в часах (30 дней)")

    # --- Файлы ---
    storage_path: Path = Field(default=Path("./storage/files"), description="Путь хранения файлов")
    thumbnails_path: Path = Field(default=Path("./storage/thumbnails"), description="Путь хранения превью")
    stickers_path: Path = Field(default=Path("./storage/stickers"), description="Путь хранения стикеров")
    max_file_size: int = Field(default=5 * 1024 * 1024 * 1024, description="Макс. размер файла (5 GB)")
    chunk_size: int = Field(default=1024 * 1024, description="Размер чанка при загрузке (1 MB)")
    thumbnail_max_size: tuple = (300, 300)
    image_preview_max_size: tuple = (800, 800)

    # --- Шифрование ---
    encryption_key_file: Path = Field(
        default=Path("./encryption.key"),
        description="Путь к файлу с ключом шифрования Fernet"
    )

    # --- Сообщения ---
    max_message_length: int = Field(default=4096, description="Макс. длина сообщения")
    messages_per_page: int = Field(default=50, description="Количество сообщений на страницу")

    # --- Опросы ---
    max_poll_options: int = Field(default=10, description="Макс. вариантов ответа в опросе")

    # --- Zeroconf ---
    zeroconf_type: str = Field(default="_lantern-chat._tcp.local.", description="Тип сервиса Zeroconf")

    class Config:
        env_prefix = "LANTERN_"
        env_file = ".env"

    def ensure_directories(self) -> None:
        """Создаёт необходимые директории если они не существуют."""
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.thumbnails_path.mkdir(parents=True, exist_ok=True)
        self.stickers_path.mkdir(parents=True, exist_ok=True)


# Глобальный экземпляр конфигурации
config = ServerConfig()