"""
Lantern v2 — WebSocket Connection Manager
Управление всеми активными WebSocket-соединениями.
Маршрутизация сообщений строго по chat_id — никакого случайного broadcast.
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Optional
from dataclasses import dataclass, field

from fastapi import WebSocket
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from server.database import (
    User, Chat, ChatMember, ChatType, UserStatus,
    async_session_factory
)


@dataclass(eq=False)
class ConnectedUser:
    """
    Информация о подключённом пользователе.

    eq=False: сравниваем по идентичности объекта (как WebSocket),
    а не по значению полей. Это делает объект hashable по id(),
    что нужно для хранения в set.
    """
    user_id: str
    username: str
    display_name: str
    websocket: WebSocket
    connected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    current_chat_id: Optional[str] = None  # В каком чате сейчас смотрит


class ConnectionManager:
    """
    Менеджер WebSocket-соединений.

    Ключевой принцип: каждое сообщение отправляется ТОЛЬКО
    участникам конкретного чата. Никакого глобального broadcast.

    Это решает проблему v1, где сообщения утекали в другие чаты.
    """

    def __init__(self):
        # user_id -> ConnectedUser
        self._connections: dict[str, set[ConnectedUser]] = {}
        # chat_id -> set of user_ids (кэш участников чатов)
        self._chat_members_cache: dict[str, set[str]] = {}
        # user_id -> set of chat_ids (в каких чатах состоит юзер)
        self._user_chats_cache: dict[str, set[str]] = {}
        # Typing indicators: (chat_id, user_id) -> asyncio.Task
        self._typing_timers: dict[tuple[str, str], asyncio.Task] = {}
        # Lock для потокобезопасности
        self._lock = asyncio.Lock()

    # ========================
    # Connection Lifecycle
    # ========================

    async def connect(
            self,
            websocket: WebSocket,
            user: User,
    ) -> ConnectedUser:
        """
        Регистрирует новое WebSocket-соединение.

        Несколько устройств одного пользователя могут быть подключены
        одновременно — каждое соединение добавляется в set.
        """
        await websocket.accept()

        connected_user = ConnectedUser(
            user_id=user.id,
            username=user.username,
            display_name=user.display_name,
            websocket=websocket,
        )

        async with self._lock:
            # Добавляем соединение в set (может быть много устройств)
            if user.id not in self._connections:
                self._connections[user.id] = set()
            self._connections[user.id].add(connected_user)

            devices_count = len(self._connections[user.id])

        print(f"[WS] {user.username} подключился "
              f"(устройств: {devices_count})")

        # Обновляем статус в БД (только если это первое устройство)
        if devices_count == 1:
            await self._update_user_status(user.id, UserStatus.ONLINE)
            await self._load_user_chats(user.id)
            await self.broadcast_status_change(user.id, UserStatus.ONLINE.value)

        return connected_user

    async def disconnect(
            self,
            user_id: str,
            websocket: Optional[WebSocket] = None,
    ) -> None:
        """
        Отключает конкретное WebSocket-соединение пользователя.

        Args:
            user_id: ID пользователя.
            websocket: Соединение для отключения.
                       Если None — отключаются ВСЕ соединения пользователя.
        """
        remaining = 0

        async with self._lock:
            user_connections = self._connections.get(user_id, set())

            if not user_connections:
                return

            if websocket is not None:
                # Удаляем конкретное соединение
                to_remove = {
                    c for c in user_connections if c.websocket is websocket
                }
                user_connections -= to_remove
            else:
                # Удаляем все (используется при force-disconnect)
                user_connections.clear()

            remaining = len(user_connections)

            # Если у пользователя не осталось соединений — убираем запись
            if not user_connections:
                self._connections.pop(user_id, None)

        # Если есть ещё устройства — НЕ трогаем статус, не чистим кэш,
        # не шлём broadcast. Пользователь всё ещё онлайн.
        if remaining > 0:
            print(f"[WS] {user_id[:8]} отключил одно устройство "
                  f"(осталось: {remaining})")
            return

        # Устройств не осталось — полный оффлайн
        print(f"[WS] {user_id[:8]} полностью отключился")

        # Очищаем typing-таймеры (теперь можно — пользователь ушёл)
        keys_to_remove = [
            key for key in self._typing_timers
            if key[1] == user_id
        ]
        for key in keys_to_remove:
            task = self._typing_timers.pop(key, None)
            if task and not task.done():
                task.cancel()

        # Обновляем статус в БД
        await self._update_user_status(user_id, UserStatus.OFFLINE)

        # Очищаем кэш чатов пользователя
        async with self._lock:
            user_chats = self._user_chats_cache.pop(user_id, set())
            for chat_id in user_chats:
                if chat_id in self._chat_members_cache:
                    self._chat_members_cache[chat_id].discard(user_id)

        # Уведомляем остальных
        await self.broadcast_status_change(user_id, UserStatus.OFFLINE.value)

    # ========================
    # Message Routing
    # ========================

    async def send_to_chat(
            self,
            chat_id: str,
            event: str,
            data: dict,
            exclude_user_id: Optional[str] = None,
    ) -> None:
        """
        Отправляет событие ВСЕМ участникам чата.

        Это ЕДИНСТВЕННЫЙ способ отправки сообщений в чат.
        Гарантирует, что сообщение попадёт только нужным людям.

        Args:
            chat_id: ID чата.
            event: Тип события (new_message, reaction_update, etc).
            data: Данные события.
            exclude_user_id: Не отправлять этому пользователю (обычно автор).
        """
        members = await self._get_chat_members(chat_id)
        message = json.dumps({"event": event, "data": data}, default=str, ensure_ascii=False)

        tasks = []
        for member_id in members:
            if member_id == exclude_user_id:
                continue

            connections = self._connections.get(member_id, set())
            for conn in connections:
                tasks.append(self._safe_send(conn.websocket, message))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def send_to_user(
            self,
            user_id: str,
            event: str,
            data: dict,
    ) -> None:
        """
        Отправляет событие конкретному пользователю.

        Args:
            user_id: ID пользователя.
            event: Тип события.
            data: Данные события.
        """
        connections = self._connections.get(user_id)
        if not connections:
            return

        message = json.dumps({"event": event, "data": data}, default=str, ensure_ascii=False)

        tasks = [self._safe_send(c.websocket, message) for c in connections]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def broadcast_to_all(
            self,
            event: str,
            data: dict,
            exclude_user_id: Optional[str] = None,
    ) -> None:
        """
        Broadcast всем подключённым пользователям.
        Используется ТОЛЬКО для глобальных событий (status_change, user_update).
        НЕ используется для сообщений чата!

        Args:
            event: Тип события.
            data: Данные.
            exclude_user_id: Исключить пользователя.
        """
        message = json.dumps({"event": event, "data": data}, default=str, ensure_ascii=False)

        tasks = []
        for user_id, connections in self._connections.items():
            if user_id == exclude_user_id:
                continue
            for conn in connections:
                tasks.append(self._safe_send(conn.websocket, message))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_send(self, websocket: WebSocket, message: str) -> None:
        """Безопасная отправка — ловит ошибки закрытого соединения."""
        try:
            await websocket.send_text(message)
        except Exception:
            pass  # Соединение уже закрыто, disconnect обработает

    # ========================
    # Typing Indicators
    # ========================

    async def set_typing(
            self,
            chat_id: str,
            user_id: str,
            username: str,
            display_name: str,
    ) -> None:
        """
        Устанавливает индикатор "печатает..." для пользователя в чате.

        Автоматически сбрасывается через 5 секунд без новых вызовов.
        Это предотвращает ложные срабатывания — индикатор показывается
        ТОЛЬКО когда пользователь реально печатает (клиент отправляет
        typing event при каждом нажатии клавиши с debounce).

        Args:
            chat_id: ID чата.
            user_id: ID печатающего пользователя.
            username: Логин.
            display_name: Отображаемое имя.
        """
        key = (chat_id, user_id)

        # Отменяем предыдущий таймер
        old_task = self._typing_timers.get(key)
        if old_task and not old_task.done():
            old_task.cancel()

        # Отправляем "печатает" участникам чата
        await self.send_to_chat(
            chat_id=chat_id,
            event="typing",
            data={
                "chat_id": chat_id,
                "user_id": user_id,
                "username": username,
                "display_name": display_name,
                "is_typing": True,
            },
            exclude_user_id=user_id,
        )

        # Устанавливаем таймер на 5 секунд для сброса
        self._typing_timers[key] = asyncio.create_task(
            self._typing_timeout(chat_id, user_id, username, display_name)
        )

    async def _typing_timeout(
            self,
            chat_id: str,
            user_id: str,
            username: str,
            display_name: str,
    ) -> None:
        """Сбрасывает индикатор печати через 5 секунд."""
        await asyncio.sleep(5)

        await self.send_to_chat(
            chat_id=chat_id,
            event="typing",
            data={
                "chat_id": chat_id,
                "user_id": user_id,
                "username": username,
                "display_name": display_name,
                "is_typing": False,
            },
            exclude_user_id=user_id,
        )

        self._typing_timers.pop((chat_id, user_id), None)

    async def stop_typing(self, chat_id: str, user_id: str) -> None:
        """Принудительно сбрасывает индикатор печати."""
        key = (chat_id, user_id)
        task = self._typing_timers.pop(key, None)
        if task and not task.done():
            task.cancel()

    # ========================
    # Status Management
    # ========================

    async def broadcast_status_change(
            self,
            user_id: str,
            new_status: str,
    ) -> None:
        """
        Уведомляет всех о смене статуса пользователя.

        Если пользователь в режиме "невидимка" — показывает его как offline.

        Args:
            user_id: ID пользователя.
            new_status: Новый статус.
        """
        # Невидимка выглядит как offline для других
        visible_status = new_status
        if new_status == UserStatus.INVISIBLE.value:
            visible_status = UserStatus.OFFLINE.value

        await self.broadcast_to_all(
            event="status_change",
            data={
                "user_id": user_id,
                "status": visible_status,
                "last_seen": datetime.now(timezone.utc).isoformat(),
            },
            exclude_user_id=None,  # Все видят, включая самого юзера
        )

    async def update_user_status(self, user_id: str, new_status: str) -> None:
        """
        Обновляет статус пользователя в БД и уведомляет других.

        Args:
            user_id: ID пользователя.
            new_status: Новый статус.
        """
        await self._update_user_status(user_id, UserStatus(new_status))
        await self.broadcast_status_change(user_id, new_status)

    # ========================
    # Chat Membership Cache
    # ========================

    async def _get_chat_members(self, chat_id: str) -> set[str]:
        """
        Получает участников чата (с кэшированием).

        Args:
            chat_id: ID чата.

        Returns:
            Множество user_id участников.
        """
        if chat_id in self._chat_members_cache:
            return self._chat_members_cache[chat_id]

        # Загружаем из БД
        async with async_session_factory() as session:
            result = await session.execute(
                select(ChatMember.user_id).where(ChatMember.chat_id == chat_id)
            )
            member_ids = {row[0] for row in result.fetchall()}

        self._chat_members_cache[chat_id] = member_ids
        return member_ids

    async def _load_user_chats(self, user_id: str) -> None:
        """Загружает чаты пользователя в кэш."""
        async with async_session_factory() as session:
            result = await session.execute(
                select(ChatMember.chat_id).where(ChatMember.user_id == user_id)
            )
            chat_ids = {row[0] for row in result.fetchall()}

        async with self._lock:
            self._user_chats_cache[user_id] = chat_ids

            # Добавляем пользователя в кэш участников каждого чата
            for chat_id in chat_ids:
                if chat_id not in self._chat_members_cache:
                    self._chat_members_cache[chat_id] = set()
                self._chat_members_cache[chat_id].add(user_id)

    async def add_to_chat_cache(self, chat_id: str, user_id: str) -> None:
        """Добавляет пользователя в кэш чата (при создании нового чата)."""
        async with self._lock:
            if chat_id not in self._chat_members_cache:
                self._chat_members_cache[chat_id] = set()
            self._chat_members_cache[chat_id].add(user_id)

            if user_id not in self._user_chats_cache:
                self._user_chats_cache[user_id] = set()
            self._user_chats_cache[user_id].add(chat_id)

    def invalidate_chat_cache(self, chat_id: str) -> None:
        """Сбрасывает кэш участников чата (при изменении состава)."""
        self._chat_members_cache.pop(chat_id, None)

    # ========================
    # DB Helpers
    # ========================

    async def _update_user_status(
            self,
            user_id: str,
            status: UserStatus,
    ) -> None:
        """Обновляет статус и last_seen пользователя в БД."""
        async with async_session_factory() as session:
            await session.execute(
                update(User)
                .where(User.id == user_id)
                .values(
                    status=status.value,
                    last_seen=datetime.now(timezone.utc),
                )
            )
            await session.commit()

    # ========================
    # Queries
    # ========================

    def is_user_online(self, user_id: str) -> bool:
        """Проверяет, подключён ли пользователь."""
        return user_id in self._connections

    def get_online_users(self) -> list[str]:
        """Возвращает список ID подключённых пользователей."""
        return list(self._connections.keys())

    @property
    def active_users_count(self) -> int:
        """Количество пользователей с хотя бы одним активным соединением."""
        return len(self._connections)

    @property
    def active_connections_count(self) -> int:
        """Общее количество активных WebSocket-соединений (все устройства)."""
        return sum(len(conns) for conns in self._connections.values())


# Глобальный экземпляр
connection_manager = ConnectionManager()
