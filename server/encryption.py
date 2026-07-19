"""
Lantern v2 — Server Encryption Module
Симметричное шифрование Fernet для сообщений и файлов.

ГАРАНТИИ:
- Ключ генерируется ОДИН раз при первом запуске
- Ключ НИКОГДА не пересоздаётся при перезапусках сервера
- Автоматический бэкап ключа (encryption.key.backup)
- Если основной файл повреждён — восстановление из бэкапа
- Если оба файла потеряны — сервер ОТКАЗЫВАЕТСЯ запускаться
  (чтобы не создать новый ключ и не сломать старые сообщения)
"""

import shutil
import sys
from pathlib import Path
from cryptography.fernet import Fernet

from server.config import config


class EncryptionManager:
    """
    Менеджер шифрования Fernet.

    Ключ загружается из файла при старте сервера.
    Если файла нет И базы данных нет — генерирует новый (первый запуск).
    Если файла нет НО база существует — ОШИБКА (ключ потерян).
    """

    def __init__(self, key_file: Path | None = None):
        self._key_file = key_file or config.encryption_key_file
        self._backup_file = Path(str(self._key_file) + ".backup")
        self._key: bytes = self._load_or_generate_key()
        self._fernet = Fernet(self._key)

    def _load_or_generate_key(self) -> bytes:
        """
        Загружает ключ. Порядок:
        1. Основной файл encryption.key
        2. Бэкап encryption.key.backup
        3. Генерация нового (ТОЛЬКО если нет БД — первый запуск)
        4. Если БД есть но ключа нет — КРИТИЧЕСКАЯ ОШИБКА
        """
        key_path = Path(self._key_file)
        backup_path = self._backup_file

        # 1. Пробуем основной файл
        if key_path.exists():
            key = self._read_and_validate(key_path)
            if key:
                # Обновляем бэкап
                self._create_backup(key_path)
                return key

        # 2. Пробуем бэкап
        if backup_path.exists():
            print("[Encryption] ⚠️  Основной ключ повреждён, восстанавливаю из бэкапа...")
            key = self._read_and_validate(backup_path)
            if key:
                # Восстанавливаем основной файл
                key_path.parent.mkdir(parents=True, exist_ok=True)
                key_path.write_bytes(key)
                print("[Encryption] ✅ Ключ восстановлен из бэкапа")
                return key

        # 3. Нет ключа вообще — проверяем, есть ли БД
        db_path = Path(config.database_url.replace("sqlite+aiosqlite:///", "").lstrip("./"))

        if db_path.exists() and db_path.stat().st_size > 0:
            # БД есть, но ключа нет — КРИТИЧЕСКАЯ ОШИБКА
            print("=" * 60)
            print("  ❌ КРИТИЧЕСКАЯ ОШИБКА: КЛЮЧ ШИФРОВАНИЯ ПОТЕРЯН!")
            print("=" * 60)
            print(f"  База данных существует: {db_path}")
            print(f"  Но файл ключа не найден: {key_path}")
            print(f"  И бэкап не найден: {backup_path}")
            print()
            print("  Все зашифрованные сообщения невозможно прочитать")
            print("  без оригинального ключа.")
            print()
            print("  Варианты:")
            print("  1. Найдите файл encryption.key и верните его")
            print("  2. Удалите БД для чистого старта:")
            print(f"     rm {db_path}")
            print("=" * 60)
            sys.exit(1)

        # 4. Первый запуск — генерируем новый ключ
        print("[Encryption] 🔑 Первый запуск — генерирую ключ шифрования...")
        key = Fernet.generate_key()

        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_bytes(key)
        self._create_backup(key_path)

        print(f"[Encryption] ✅ Ключ сохранён: {key_path}")
        print(f"[Encryption] ✅ Бэкап создан: {backup_path}")
        print(f"[Encryption] ⚠️  ВАЖНО: НЕ УДАЛЯЙТЕ файл {key_path}")

        return key

    def _read_and_validate(self, path: Path) -> bytes | None:
        """Читает ключ из файла и валидирует."""
        try:
            key = path.read_bytes().strip()
            Fernet(key)  # Проверяем что это настоящий Fernet-ключ
            return key
        except (ValueError, Exception) as e:
            print(f"[Encryption] ⚠️  Файл {path} повреждён: {e}")
            return None

    def _create_backup(self, source: Path) -> None:
        """Создаёт бэкап ключа."""
        try:
            shutil.copy2(source, self._backup_file)
        except Exception as e:
            print(f"[Encryption] ⚠️  Не удалось создать бэкап: {e}")

    def encrypt(self, data: str) -> str:
        """Шифрует строку."""
        if not data:
            return ""
        encrypted = self._fernet.encrypt(data.encode("utf-8"))
        return encrypted.decode("utf-8")

    def decrypt(self, encrypted_data: str) -> str:
        """Расшифровывает строку."""
        if not encrypted_data:
            return ""
        try:
            decrypted = self._fernet.decrypt(encrypted_data.encode("utf-8"))
            return decrypted.decode("utf-8")
        except Exception:
            return "[Ошибка расшифровки]"

    def encrypt_bytes(self, data: bytes) -> bytes:
        """Шифрует байты."""
        if not data:
            return b""
        return self._fernet.encrypt(data)

    def decrypt_bytes(self, encrypted_data: bytes) -> bytes:
        """Расшифровывает байты."""
        if not encrypted_data:
            return b""
        try:
            return self._fernet.decrypt(encrypted_data)
        except Exception:
            return b""

    @property
    def key_exists(self) -> bool:
        """Проверяет, существует ли файл ключа."""
        return Path(self._key_file).exists()

    def verify_integrity(self) -> bool:
        """
        Проверяет целостность: шифрует и расшифровывает тестовую строку.
        Вызывается при старте сервера.
        """
        test_string = "lantern_v2_integrity_check_🏮"
        try:
            encrypted = self.encrypt(test_string)
            decrypted = self.decrypt(encrypted)
            return decrypted == test_string
        except Exception:
            return False


# Глобальный экземпляр — создаётся при импорте
encryption_manager = EncryptionManager()