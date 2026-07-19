"""
Lantern v2 — Client-side Encryption
Клиентская обёртка шифрования.
Ключ получается с сервера при подключении и хранится в памяти.
"""


class ClientEncryption:
    """
    Клиентское шифрование.

    В текущей архитектуре (симметричное Fernet) шифрование
    происходит на стороне сервера. Клиент работает с открытым текстом.

    Этот класс зарезервирован для будущего E2E-шифрования,
    а сейчас просто предоставляет pass-through методы.
    """

    def __init__(self):
        self._ready = False

    def set_ready(self) -> None:
        """Отмечает, что шифрование готово к работе."""
        self._ready = True

    @property
    def is_ready(self) -> bool:
        return self._ready

    def prepare_message(self, text: str) -> str:
        """
        Подготавливает сообщение к отправке.
        В текущей архитектуре — просто возвращает текст как есть.
        Сервер сам зашифрует при сохранении в БД.
        """
        return text

    def process_received(self, text: str) -> str:
        """
        Обрабатывает полученное сообщение.
        В текущей архитектуре — возвращает как есть (сервер расшифровал).
        """
        return text if text else ""


client_encryption = ClientEncryption()