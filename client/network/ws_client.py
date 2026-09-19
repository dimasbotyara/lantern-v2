"""
Lantern v2 — WebSocket Client
Асинхронный WebSocket-клиент с автоматическим переподключением.
Поддерживает анимацию луны при потере соединения 🌑🌒🌓🌔🌕🌖🌗🌘
"""

import asyncio
import json
from typing import Optional, Callable
from dataclasses import dataclass, field
from enum import Enum

import aiohttp


class WSState(Enum):
    """Состояния WebSocket-соединения."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"


@dataclass
class WSCallbacks:
    """Callbacks для событий WebSocket."""
    # Состояние соединения
    on_connected: Optional[Callable] = None
    on_disconnected: Optional[Callable] = None
    on_reconnecting: Optional[Callable] = None          # принимает int (attempt)
    on_reconnected: Optional[Callable] = None
    on_connection_failed: Optional[Callable] = None      # принимает str (error)
    on_kicked: Optional[Callable] = None

    # Сообщения
    on_new_message: Optional[Callable] = None             # принимает dict
    on_message_edited: Optional[Callable] = None          # принимает dict
    on_message_deleted: Optional[Callable] = None         # принимает dict

    # Реакции
    on_reaction_update: Optional[Callable] = None         # принимает dict

    # Typing
    on_typing: Optional[Callable] = None                  # принимает dict

    # Статус
    on_status_change: Optional[Callable] = None           # принимает dict

    # Опросы
    on_poll_update: Optional[Callable] = None             # принимает dict

    # Закреплённые
    on_pin_update: Optional[Callable] = None              # принимает dict

    # Обновление пользователя
    on_user_update: Optional[Callable] = None             # принимает dict

    # Ошибки
    on_error: Optional[Callable] = None                   # принимает dict


class WebSocketClient:
    """
    WebSocket-клиент с автопереподключением.

    При потере соединения пытается переподключиться 30 секунд.
    Уведомляет клиент о состоянии через callbacks.

    Фазы переподключения:
    1. Соединение потеряно → state = RECONNECTING
    2. Попытки каждые 2 секунды в течение 30 секунд
    3. Если успешно → state = CONNECTED, on_reconnected()
    4. Если не удалось → state = DISCONNECTED, on_connection_failed()
    """

    # Лунные фазы для анимации переподключения
    MOON_PHASES = ["🌑", "🌒", "🌓", "🌔", "🌕", "🌖", "🌗", "🌘"]

    def __init__(self):
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._state = WSState.DISCONNECTED
        self._callbacks = WSCallbacks()
        self._host: Optional[str] = None
        self._port: Optional[int] = None
        self._token: Optional[str] = None
        self._receive_task: Optional[asyncio.Task] = None
        self._reconnect_task: Optional[asyncio.Task] = None
        self._typing_task: Optional[asyncio.Task] = None
        self._last_typing_time: float = 0

        # Reconnection settings
        self._max_reconnect_time = 30  # секунд
        self._reconnect_interval = 2  # секунд между попытками
        self._should_reconnect = True

        # Moon phase animation
        self._moon_phase_index = 0

    # ========================
    # Properties
    # ========================

    @property
    def state(self) -> WSState:
        return self._state

    @property
    def is_connected(self) -> bool:
        return self._state == WSState.CONNECTED

    @property
    def callbacks(self) -> WSCallbacks:
        return self._callbacks

    @property
    def current_moon_phase(self) -> str:
        """Текущая фаза луны для анимации переподключения."""
        return self.MOON_PHASES[self._moon_phase_index % len(self.MOON_PHASES)]

    def set_callbacks(self, callbacks: WSCallbacks) -> None:
        """Устанавливает callbacks."""
        self._callbacks = callbacks

    # ========================
    # Connection
    # ========================

    async def connect(self, host: str, port: int, token: str) -> bool:
        """
        Подключается к WebSocket-серверу.

        Args:
            host: IP-адрес сервера.
            port: Порт сервера.
            token: JWT-токен для аутентификации.

        Returns:
            True если подключение успешно.
        """
        self._host = host
        self._port = port
        self._token = token
        self._should_reconnect = True
        self._state = WSState.CONNECTING

        success = await self._do_connect()

        if success:
            self._state = WSState.CONNECTED
            if self._callbacks.on_connected:
                self._callbacks.on_connected()

            # Запускаем приём сообщений
            self._receive_task = asyncio.create_task(self._receive_loop())
            return True
        else:
            self._state = WSState.DISCONNECTED
            return False

    async def _do_connect(self) -> bool:
        """Выполняет подключение к WebSocket."""
        try:
            if self._session is None or self._session.closed:
                self._session = aiohttp.ClientSession()

            url = f"ws://{self._host}:{self._port}/ws?token={self._token}"

            self._ws = await self._session.ws_connect(
                url,
                heartbeat=30,
                receive_timeout=60,
            )
            return True

        except Exception as e:
            print(f"[WS] Ошибка подключения: {e}")
            return False

    async def disconnect(self) -> None:
        """Отключается от WebSocket."""
        self._should_reconnect = False

        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass

        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        if self._ws and not self._ws.closed:
            await self._ws.close()
            self._ws = None

        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

        self._state = WSState.DISCONNECTED

        if self._callbacks.on_disconnected:
            self._callbacks.on_disconnected()

    # ========================
    # Receive Loop
    # ========================

    async def _receive_loop(self) -> None:
        """Основной цикл приёма сообщений."""
        kicked = False  # ← флаг: нас выкинули осознанно?
        kick_reason = ""

        try:
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._handle_message(msg.data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    print(f"[WS] Ошибка: {self._ws.exception()}")
                    break
                elif msg.type == aiohttp.WSMsgType.CLOSE:
                    # Проверяем код закрытия
                    close_code = msg.data  # int
                    close_reason = msg.extra  # str

                    if close_code == 4001:
                        kicked = True
                        kick_reason = close_reason or "Вход с другого клиента"
                        print(f"[WS] Кикнут сервером: {kick_reason}")
                    break
                elif msg.type == aiohttp.WSMsgType.CLOSING:
                    break
        except asyncio.CancelledError:
            return
        except Exception as e:
            print(f"[WS] Ошибка в receive loop: {e}")

        # Если нас выкинули осознанно — не переподключаемся
        if kicked:
            self._should_reconnect = False
            self._state = WSState.DISCONNECTED

            if self._callbacks.on_kicked:
                self._callbacks.on_kicked(kick_reason)
            return

        # Иначе — обычная потеря связи, пытаемся переподключиться
        if self._should_reconnect:
            await self._start_reconnecting()

    async def _handle_message(self, raw: str) -> None:
        """Обрабатывает входящее JSON-сообщение и вызывает соответствующий callback."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return

        event = data.get("event", "")
        payload = data.get("data", {})

        callback_map = {
            "new_message": self._callbacks.on_new_message,
            "message_edited": self._callbacks.on_message_edited,
            "message_deleted": self._callbacks.on_message_deleted,
            "reaction_update": self._callbacks.on_reaction_update,
            "typing": self._callbacks.on_typing,
            "status_change": self._callbacks.on_status_change,
            "poll_update": self._callbacks.on_poll_update,
            "pin_update": self._callbacks.on_pin_update,
            "user_update": self._callbacks.on_user_update,
            "error": self._callbacks.on_error,
        }

        callback = callback_map.get(event)
        if callback:
            try:
                callback(payload)
            except Exception as e:
                print(f"[WS] Ошибка в callback {event}: {e}")

    # ========================
    # Reconnection
    # ========================

    async def _start_reconnecting(self) -> None:
        """
        Запускает процесс переподключения.
        Попытки каждые 2 секунды в течение 30 секунд.
        Анимация лунных фаз обновляется каждую попытку.
        """
        if not self._should_reconnect:
            return

        self._state = WSState.RECONNECTING
        self._moon_phase_index = 0

        max_attempts = self._max_reconnect_time // self._reconnect_interval
        attempt = 0

        while attempt < max_attempts and self._should_reconnect:
            attempt += 1
            self._moon_phase_index = attempt % len(self.MOON_PHASES)

            if self._callbacks.on_reconnecting:
                self._callbacks.on_reconnecting(attempt)

            # Пытаемся переподключиться
            if self._ws and not self._ws.closed:
                try:
                    await self._ws.close()
                except Exception:
                    pass

            success = await self._do_connect()

            if success:
                self._state = WSState.CONNECTED

                if self._callbacks.on_reconnected:
                    self._callbacks.on_reconnected()

                # Перезапускаем receive loop
                self._receive_task = asyncio.create_task(self._receive_loop())
                return

            # Ждём перед следующей попыткой
            await asyncio.sleep(self._reconnect_interval)

        # Не удалось переподключиться
        self._state = WSState.DISCONNECTED

        if self._callbacks.on_connection_failed:
            self._callbacks.on_connection_failed(
                f"Не удалось переподключиться за {self._max_reconnect_time} секунд"
            )

    # ========================
    # Send Events
    # ========================

    async def send_event(self, event: str, data: dict) -> bool:
        """
        Отправляет событие на сервер.

        Args:
            event: Тип события.
            data: Данные события.

        Returns:
            True если отправлено успешно.
        """
        if not self.is_connected or self._ws is None or self._ws.closed:
            return False

        try:
            message = json.dumps({"event": event, "data": data}, ensure_ascii=False)
            await self._ws.send_str(message)
            return True
        except Exception as e:
            print(f"[WS] Ошибка отправки: {e}")
            return False

    async def send_message(
            self,
            chat_id: str,
            content: str,
            reply_to_id: Optional[str] = None,
    ) -> bool:
        """Отправить текстовое сообщение."""
        return await self.send_event("send_message", {
            "chat_id": chat_id,
            "content": content,
            "reply_to_id": reply_to_id,
        })

    async def edit_message(self, message_id: str, new_content: str) -> bool:
        """Редактировать сообщение."""
        return await self.send_event("edit_message", {
            "message_id": message_id,
            "new_content": new_content,
        })

    async def delete_message(self, message_id: str, for_everyone: bool = False) -> bool:
        """Удалить сообщение."""
        return await self.send_event("delete_message", {
            "message_id": message_id,
            "for_everyone": for_everyone,
        })

    async def toggle_reaction(self, message_id: str, emoji: str) -> bool:
        """Добавить/убрать реакцию."""
        return await self.send_event("toggle_reaction", {
            "message_id": message_id,
            "emoji": emoji,
        })

    async def send_typing(self, chat_id: str) -> bool:
        """
        Отправить индикатор печати.
        Дебаунсится — не отправляет чаще раза в секунду.
        """
        import time
        now = time.time()

        if now - self._last_typing_time < 1.0:
            return True  # Пропускаем (debounce)

        self._last_typing_time = now
        return await self.send_event("typing", {"chat_id": chat_id})

    async def set_status(
            self,
            status: str,
            custom_text: Optional[str] = None,
    ) -> bool:
        """Установить статус."""
        return await self.send_event("set_status", {
            "status": status,
            "custom_text": custom_text,
        })

    async def pin_message(self, message_id: str, chat_id: str) -> bool:
        """Закрепить сообщение."""
        return await self.send_event("pin_message", {
            "message_id": message_id,
            "chat_id": chat_id,
        })

    async def unpin_message(self, message_id: str, chat_id: str) -> bool:
        """Открепить сообщение."""
        return await self.send_event("unpin_message", {
            "message_id": message_id,
            "chat_id": chat_id,
        })

    async def send_sticker(
            self,
            chat_id: str,
            sticker_id: str,
            reply_to_id: Optional[str] = None,
    ) -> bool:
        """Отправить стикер."""
        return await self.send_event("send_sticker", {
            "chat_id": chat_id,
            "sticker_id": sticker_id,
            "reply_to_id": reply_to_id,
        })

    async def forward_messages(
            self,
            message_ids: list[str],
            target_chat_id: str,
    ) -> bool:
        """Переслать сообщения."""
        return await self.send_event("forward_messages", {
            "message_ids": message_ids,
            "target_chat_id": target_chat_id,
        })

    async def create_poll(
            self,
            chat_id: str,
            question: str,
            options: list[str],
            is_anonymous: bool = False,
            is_multiple_choice: bool = False,
    ) -> bool:
        """Создать опрос."""
        return await self.send_event("create_poll", {
            "chat_id": chat_id,
            "question": question,
            "options": options,
            "is_anonymous": is_anonymous,
            "is_multiple_choice": is_multiple_choice,
        })

    async def vote_poll(self, poll_id: str, option_ids: list[str]) -> bool:
        """Голосовать в опросе."""
        return await self.send_event("vote_poll", {
            "poll_id": poll_id,
            "option_ids": option_ids,
        })

    async def mark_read(self, chat_id: str, last_message_id: str) -> bool:
        """Отметить сообщения как прочитанные."""
        return await self.send_event("mark_read", {
            "chat_id": chat_id,
            "last_message_id": last_message_id,
        })


# Глобальный экземпляр
ws_client = WebSocketClient()
