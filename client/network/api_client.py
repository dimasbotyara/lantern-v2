"""
Lantern v2 — HTTP API Client
Асинхронный HTTP-клиент для взаимодействия с REST API сервера.
"""

import asyncio
import aiohttp
from pathlib import Path
from typing import Optional, Any
from dataclasses import dataclass


@dataclass
class ApiResponse:
    """Ответ API."""
    success: bool
    status: int
    data: Any = None
    error: Optional[str] = None


class ApiClient:
    """
    Асинхронный HTTP-клиент для Lantern v2 REST API.

    Все методы возвращают ApiResponse.
    Токен автоматически добавляется в заголовки после авторизации.
    """

    def __init__(self):
        self._base_url: Optional[str] = None
        self._token: Optional[str] = None
        self._session: Optional[aiohttp.ClientSession] = None

    # ========================
    # Connection
    # ========================

    async def connect(self, host: str, port: int) -> None:
        """
        Устанавливает базовый URL и создаёт HTTP-сессию.

        Args:
            host: IP-адрес сервера.
            port: Порт сервера.
        """
        self._base_url = f"http://{host}:{port}"
        await self._ensure_session()

    async def _ensure_session(self) -> None:
        """Создаёт aiohttp-сессию если её нет."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            self._session = aiohttp.ClientSession(timeout=timeout)

    async def close(self) -> None:
        """Закрывает HTTP-сессию."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    def set_token(self, token: str) -> None:
        """Устанавливает JWT-токен для авторизации."""
        self._token = token

    def clear_token(self) -> None:
        """Очищает токен."""
        self._token = None

    @property
    def is_connected(self) -> bool:
        return self._base_url is not None

    @property
    def base_url(self) -> Optional[str]:
        return self._base_url

    def _headers(self) -> dict:
        """Формирует заголовки запроса."""
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    # ========================
    # Generic Request
    # ========================

    async def _request(
            self,
            method: str,
            endpoint: str,
            json_data: Optional[dict] = None,
            params: Optional[dict] = None,
            data: Optional[aiohttp.FormData] = None,
    ) -> ApiResponse:
        """
        Выполняет HTTP-запрос.

        Args:
            method: HTTP-метод (GET, POST, PUT, DELETE).
            endpoint: Путь API (например, /api/auth/login).
            json_data: JSON-тело запроса.
            params: Query-параметры.
            data: Form-data (для загрузки файлов).

        Returns:
            ApiResponse с результатом.
        """
        if not self._base_url:
            return ApiResponse(success=False, status=0, error="Не подключён к серверу")

        await self._ensure_session()

        url = f"{self._base_url}{endpoint}"

        try:
            headers = self._headers()
            if data:
                # Для FormData не нужен Content-Type (aiohttp поставит multipart)
                headers.pop("Content-Type", None)

            async with self._session.request(
                    method=method,
                    url=url,
                    json=json_data,
                    params=params,
                    data=data,
                    headers=headers,
            ) as response:
                status = response.status

                # Пытаемся прочитать JSON
                try:
                    response_data = await response.json()
                except (aiohttp.ContentTypeError, Exception):
                    response_data = await response.text()

                if 200 <= status < 300:
                    return ApiResponse(
                        success=True,
                        status=status,
                        data=response_data,
                    )
                else:
                    error_msg = "Неизвестная ошибка"
                    if isinstance(response_data, dict):
                        error_msg = response_data.get("detail", str(response_data))
                    elif isinstance(response_data, str):
                        error_msg = response_data

                    return ApiResponse(
                        success=False,
                        status=status,
                        error=error_msg,
                    )

        except aiohttp.ClientConnectorError:
            return ApiResponse(
                success=False, status=0,
                error="Не удалось подключиться к серверу"
            )
        except asyncio.TimeoutError:
            return ApiResponse(
                success=False, status=0,
                error="Таймаут соединения"
            )
        except Exception as e:
            return ApiResponse(
                success=False, status=0,
                error=f"Ошибка запроса: {str(e)}"
            )

    # ========================
    # Ping
    # ========================

    async def ping(self) -> ApiResponse:
        """Проверяет доступность сервера."""
        return await self._request("GET", "/api/ping")

    # ========================
    # Auth
    # ========================

    async def register(
            self,
            username: str,
            password: str,
            display_name: str,
            nick_color: str = "#cba6f7",
    ) -> ApiResponse:
        """Регистрация нового пользователя."""
        result = await self._request("POST", "/api/auth/register", json_data={
            "username": username,
            "password": password,
            "display_name": display_name,
            "nick_color": nick_color,
        })

        if result.success and isinstance(result.data, dict):
            token = result.data.get("token")
            if token:
                self.set_token(token)

        return result

    async def login(self, username: str, password: str) -> ApiResponse:
        """Вход в аккаунт."""
        result = await self._request("POST", "/api/auth/login", json_data={
            "username": username,
            "password": password,
        })

        if result.success and isinstance(result.data, dict):
            token = result.data.get("token")
            if token:
                self.set_token(token)

        return result

    async def verify_token(self) -> ApiResponse:
        """Проверяет валидность текущего токена."""
        return await self._request("POST", "/api/auth/verify-token")

    async def get_me(self) -> ApiResponse:
        """Получить информацию о текущем пользователе."""
        return await self._request("GET", "/api/auth/me")

    async def update_profile(
            self,
            display_name: Optional[str] = None,
            nick_color: Optional[str] = None,
            custom_status_text: Optional[str] = None,
            status: Optional[str] = None,
    ) -> ApiResponse:
        """Обновить профиль."""
        data = {}
        if display_name is not None:
            data["display_name"] = display_name
        if nick_color is not None:
            data["nick_color"] = nick_color
        if custom_status_text is not None:
            data["custom_status_text"] = custom_status_text
        if status is not None:
            data["status"] = status
        return await self._request("PUT", "/api/auth/me", json_data=data)

    async def upload_avatar(self, file_path: str) -> ApiResponse:
        """Загрузить аватар."""
        path = Path(file_path)
        if not path.exists():
            return ApiResponse(success=False, status=0, error="Файл не найден")

        # Проверяем размер до чтения (защита от OOM)
        max_avatar_size = 5 * 1024 * 1024  # 5 MB (как на сервере)
        file_size = path.stat().st_size
        if file_size > max_avatar_size:
            return ApiResponse(
                success=False, status=0,
                error=f"Аватар слишком большой ({file_size // 1024 // 1024} MB, "
                      f"максимум {max_avatar_size // 1024 // 1024} MB)"
            )

        # Определяем MIME-тип по расширению
        import mimetypes
        mime_type = mimetypes.guess_type(str(path))[0] or "image/png"

        with open(path, "rb") as f:
            file_bytes = f.read()

        data = aiohttp.FormData()
        data.add_field(
            "file",
            file_bytes,
            filename=path.name,
            content_type=mime_type,
        )
        return await self._request("POST", "/api/auth/me/avatar", data=data)

    async def get_all_users(self) -> ApiResponse:
        """Получить список всех пользователей."""
        return await self._request("GET", "/api/auth/users")

    async def get_user(self, user_id: str) -> ApiResponse:
        """Получить информацию о пользователе."""
        return await self._request("GET", f"/api/auth/users/{user_id}")

    # ========================
    # Chats
    # ========================

    async def get_chats(self) -> ApiResponse:
        """Получить список всех чатов."""
        return await self._request("GET", "/api/chats")

    async def create_direct_chat(self, target_user_id: str) -> ApiResponse:
        """Создать личный чат."""
        return await self._request("POST", "/api/chats/direct", json_data={
            "target_user_id": target_user_id,
        })

    async def get_messages(
            self,
            chat_id: str,
            before: Optional[str] = None,
            limit: int = 50,
    ) -> ApiResponse:
        """Получить историю сообщений."""
        params = {"limit": limit}
        if before:
            params["before"] = before
        return await self._request("GET", f"/api/chats/{chat_id}/messages", params=params)

    async def search_messages(
            self,
            chat_id: str,
            query: str,
            page: int = 1,
            per_page: int = 20,
    ) -> ApiResponse:
        """Поиск по сообщениям в чате."""
        return await self._request("GET", f"/api/chats/{chat_id}/search", params={
            "q": query,
            "page": page,
            "per_page": per_page,
        })

    async def get_pinned_messages(self, chat_id: str) -> ApiResponse:
        """Получить закреплённые сообщения."""
        return await self._request("GET", f"/api/chats/{chat_id}/pinned")

    async def mark_chat_read(self, chat_id: str) -> ApiResponse:
        """Отметить чат как прочитанный."""
        return await self._request("POST", f"/api/chats/{chat_id}/mark-read")

    async def get_sticker_packs(self) -> ApiResponse:
        """Получить наборы стикеров."""
        return await self._request("GET", "/api/chats/stickers/packs")

    # ========================
    # Files
    # ========================

    async def upload_file(
            self,
            chat_id: str,
            file_path: str,
            reply_to_id: Optional[str] = None,
            on_progress: Optional[callable] = None,
    ) -> ApiResponse:
        """
        Загрузить файл.
        Для файлов < 50 MB — простая загрузка.
        Для больших — чанковая.

        Args:
            chat_id: ID чата.
            file_path: Путь к файлу.
            reply_to_id: ID сообщения для ответа.
            on_progress: Callback прогресса (0.0 — 1.0).
        """
        path = Path(file_path)
        if not path.exists():
            return ApiResponse(success=False, status=0, error="Файл не найден")

        file_size = path.stat().st_size

        # Простая загрузка для маленьких файлов
        if file_size <= 50 * 1024 * 1024:  # 50 MB
            return await self._upload_simple(chat_id, path, reply_to_id, on_progress)
        else:
            return await self._upload_chunked(chat_id, path, file_size, reply_to_id, on_progress)

    async def _upload_simple(
            self,
            chat_id: str,
            file_path: Path,
            reply_to_id: Optional[str],
            on_progress: Optional[callable],
    ) -> ApiResponse:
        """Простая загрузка файла (для файлов до 50 MB)."""
        # Защита: этот метод не должен вызываться для больших файлов
        max_simple_size = 50 * 1024 * 1024  # 50 MB
        file_size = file_path.stat().st_size
        if file_size > max_simple_size:
            return ApiResponse(
                success=False, status=0,
                error=f"Файл слишком большой для простой загрузки ({file_size} байт)"
            )

        # Читаем в память ТОЛЬКО маленькие файлы (до 50 MB)
        with open(file_path, "rb") as f:
            file_bytes = f.read()

        data = aiohttp.FormData()
        data.add_field("chat_id", chat_id)
        data.add_field(
            "file",
            file_bytes,
            filename=file_path.name,
        )
        if reply_to_id:
            data.add_field("reply_to_id", reply_to_id)

        if on_progress:
            on_progress(0.5)

        result = await self._request("POST", "/api/files/upload", data=data)

        if on_progress:
            on_progress(1.0)

        return result

    async def _upload_chunked(
            self,
            chat_id: str,
            file_path: Path,
            file_size: int,
            reply_to_id: Optional[str],
            on_progress: Optional[callable],
    ) -> ApiResponse:
        """Чанковая загрузка большого файла."""
        import mimetypes

        chunk_size = 1024 * 1024  # 1 MB
        total_chunks = (file_size + chunk_size - 1) // chunk_size

        mime_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"

        # Инициализация
        init_result = await self._request("POST", "/api/files/upload/init", json_data={
            "chat_id": chat_id,
            "filename": file_path.name,
            "file_size": file_size,
            "mime_type": mime_type,
            "total_chunks": total_chunks,
            "reply_to_id": reply_to_id,
        })

        if not init_result.success:
            return init_result

        upload_id = init_result.data.get("upload_id")

        # Загружаем чанки
        with open(file_path, "rb") as f:
            for chunk_index in range(total_chunks):
                chunk_data = f.read(chunk_size)

                form = aiohttp.FormData()
                form.add_field("chunk_index", str(chunk_index))
                form.add_field(
                    "chunk",
                    chunk_data,
                    filename=f"chunk_{chunk_index}",
                )

                chunk_result = await self._request(
                    "POST",
                    f"/api/files/upload/chunk/{upload_id}",
                    data=form,
                )

                if not chunk_result.success:
                    return chunk_result

                if on_progress:
                    progress = (chunk_index + 1) / total_chunks
                    on_progress(progress)

        return ApiResponse(
            success=True,
            status=200,
            data={"upload_id": upload_id, "complete": True},
        )

    async def download_file(
            self,
            file_id: str,
            save_path: str,
            on_progress: Optional[callable] = None,
    ) -> ApiResponse:
        """
        Скачать файл.

        Args:
            file_id: ID файла (attachment_id).
            save_path: Путь для сохранения.
            on_progress: Callback прогресса.
        """
        if not self._base_url:
            return ApiResponse(success=False, status=0, error="Не подключён")

        await self._ensure_session()

        url = f"{self._base_url}/api/files/download/{file_id}"
        headers = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        try:
            async with self._session.get(url, headers=headers) as response:
                if response.status != 200:
                    return ApiResponse(
                        success=False,
                        status=response.status,
                        error="Ошибка скачивания"
                    )

                total_size = int(response.headers.get("content-length", 0))
                downloaded = 0

                save = Path(save_path)
                save.parent.mkdir(parents=True, exist_ok=True)

                with open(save, "wb") as f:
                    async for chunk in response.content.iter_chunked(1024 * 1024):
                        f.write(chunk)
                        downloaded += len(chunk)

                        if on_progress and total_size > 0:
                            on_progress(downloaded / total_size)

                return ApiResponse(
                    success=True,
                    status=200,
                    data={"path": str(save)},
                )

        except Exception as e:
            return ApiResponse(success=False, status=0, error=str(e))

    async def get_thumbnail_url(self, file_id: str) -> str:
        """Возвращает URL превью файла."""
        return f"{self._base_url}/api/files/thumbnail/{file_id}"

    async def get_avatar_url(self, user_id: str) -> str:
        """Возвращает URL аватара пользователя."""
        return f"{self._base_url}/api/files/avatar/{user_id}"

    async def get_sticker_url(self, sticker_id: str) -> str:
        """Возвращает URL стикера."""
        return f"{self._base_url}/api/files/sticker/{sticker_id}"

    async def download_bytes(self, url: str) -> Optional[bytes]:
        """
        Скачивает данные по URL (для превью, аватаров и т.д.).

        Args:
            url: Полный URL.

        Returns:
            Байты или None при ошибке.
        """
        await self._ensure_session()

        headers = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        try:
            async with self._session.get(url, headers=headers) as response:
                if response.status == 200:
                    return await response.read()
                return None
        except Exception:
            return None


# Глобальный экземпляр
api_client = ApiClient()
