"""
Lantern v2 — WebSocket Event Handler
Обрабатывает все входящие WebSocket-события от клиентов.

Поддерживаемые события:
- send_message: Отправка текстового сообщения
- edit_message: Редактирование сообщения
- delete_message: Удаление сообщения
- toggle_reaction: Добавить/убрать реакцию
- typing: Индикатор печати
- set_status: Смена статуса
- pin_message: Закрепить сообщение
- unpin_message: Открепить сообщение
- send_sticker: Отправка стикера
- forward_messages: Пересылка сообщений
- vote_poll: Голосование в опросе
- mark_read: Отметить прочитанным
"""

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import WebSocket
from sqlalchemy import select, update, delete, func, and_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from server.database import (
    User, Chat, ChatMember, Message, MessageType, ChatType,
    Reaction, PinnedMessage, FileAttachment, Poll, PollOption,
    PollVote, Sticker, StickerUsage, ReadState,
    async_session_factory, generate_uuid, utcnow
)
from server.models import (
    MessageResponse, UserResponse, MessageReplyInfo,
    ReactionInfo, FileAttachmentResponse, PollResponse,
    PollOptionResponse, StickerResponse, PinnedMessageResponse
)
from server.encryption import encryption_manager
from server.websocket.manager import ConnectionManager, ConnectedUser


class WebSocketHandler:
    """
    Обработчик WebSocket-событий.

    Каждый метод handle_* обрабатывает конкретный тип события.
    Все сообщения маршрутизируются строго по chat_id через ConnectionManager.
    """

    def __init__(self, manager: ConnectionManager):
        self.manager = manager

    async def handle_event(
            self,
            connected_user: ConnectedUser,
            raw_message: str,
    ) -> None:
        """
        Главный диспетчер событий.
        Парсит JSON и вызывает соответствующий обработчик.

        Args:
            connected_user: Подключённый пользователь.
            raw_message: Сырой JSON от клиента.
        """
        try:
            data = json.loads(raw_message)
        except json.JSONDecodeError:
            await self.manager.send_to_user(
                connected_user.user_id,
                "error",
                {"message": "Невалидный JSON"}
            )
            return

        event = data.get("event", "")
        if not isinstance(event, str) or not event:
            await self.manager.send_to_user(
                connected_user.user_id,
                "error",
                {"message": "Отсутствует поле 'event'"},
            )
            return

        payload = data.get("data", {})
        if not isinstance(payload, dict):
            await self.manager.send_to_user(
                connected_user.user_id,
                "error",
                {"message": "Поле 'data' должно быть объектом"},
            )
            return

        # Диспетчер событий
        handlers = {
            "send_message": self.handle_send_message,
            "edit_message": self.handle_edit_message,
            "delete_message": self.handle_delete_message,
            "toggle_reaction": self.handle_toggle_reaction,
            "typing": self.handle_typing,
            "set_status": self.handle_set_status,
            "pin_message": self.handle_pin_message,
            "unpin_message": self.handle_unpin_message,
            "send_sticker": self.handle_send_sticker,
            "forward_messages": self.handle_forward_messages,
            "vote_poll": self.handle_vote_poll,
            "mark_read": self.handle_mark_read,
            "create_poll": self.handle_create_poll,
        }

        handler = handlers.get(event)
        if handler is None:
            await self.manager.send_to_user(
                connected_user.user_id,
                "error",
                {"message": f"Неизвестное событие: {event}"}
            )
            return

        try:
            await handler(connected_user, payload)
        except Exception as e:
            print(f"[WS Error] {event}: {e}")
            await self.manager.send_to_user(
                connected_user.user_id,
                "error",
                {"message": f"Ошибка обработки {event}: {str(e)}"}
            )

    # ========================
    # Send Message
    # ========================

    async def handle_send_message(
            self,
            connected_user: ConnectedUser,
            payload: dict,
    ) -> None:
        """
        Обработка отправки текстового сообщения.

        Payload:
            chat_id: str
            content: str
            reply_to_id: Optional[str]
        """
        chat_id = payload.get("chat_id")
        content = payload.get("content", "").strip()
        reply_to_id = payload.get("reply_to_id")

        if not chat_id or not content:
            return

        # Ограничение длины
        if len(content) > 4096:
            await self.manager.send_to_user(
                connected_user.user_id,
                "error",
                {"message": "Сообщение слишком длинное (макс. 4096 символов)"}
            )
            return

        async with async_session_factory() as session:
            # Проверяем что пользователь — участник чата
            is_member = await self._check_membership(
                session, chat_id, connected_user.user_id
            )
            if not is_member:
                return

            # Шифруем контент
            encrypted_content = encryption_manager.encrypt(content)

            # Создаём сообщение
            message = Message(
                id=generate_uuid(),
                chat_id=chat_id,
                author_id=connected_user.user_id,
                message_type=MessageType.TEXT.value,
                content_encrypted=encrypted_content,
                reply_to_id=reply_to_id,
            )
            session.add(message)
            await session.commit()

            # Формируем ответ
            response = await self._build_message_response(
                session, message, connected_user.user_id
            )

        # Останавливаем typing
        await self.manager.stop_typing(chat_id, connected_user.user_id)

        # Отправляем ВСЕМ участникам чата (включая автора)
        await self.manager.send_to_chat(
            chat_id=chat_id,
            event="new_message",
            data=response,
        )

    # ========================
    # Edit Message
    # ========================

    async def handle_edit_message(
            self,
            connected_user: ConnectedUser,
            payload: dict,
    ) -> None:
        """
        Редактирование сообщения.
        Только автор может редактировать своё сообщение.

        Payload:
            message_id: str
            new_content: str
        """
        message_id = payload.get("message_id")
        new_content = payload.get("new_content", "").strip()

        if not message_id or not new_content:
            return

        if len(new_content) > 4096:
            return

        async with async_session_factory() as session:
            result = await session.execute(
                select(Message).where(
                    Message.id == message_id,
                    Message.author_id == connected_user.user_id,
                    Message.is_deleted == False,
                )
            )
            message = result.scalar_one_or_none()

            if message is None:
                return

            # Обновляем
            encrypted_content = encryption_manager.encrypt(new_content)
            message.content_encrypted = encrypted_content
            message.is_edited = True
            message.edited_at = utcnow()

            session.add(message)
            await session.commit()

            chat_id = message.chat_id

        # Уведомляем чат
        await self.manager.send_to_chat(
            chat_id=chat_id,
            event="message_edited",
            data={
                "message_id": message_id,
                "chat_id": chat_id,
                "new_content": new_content,
                "is_edited": True,
            },
        )

    # ========================
    # Delete Message
    # ========================

    async def handle_delete_message(
            self,
            connected_user: ConnectedUser,
            payload: dict,
    ) -> None:
        """
        Удаление сообщения.

        Payload:
            message_id: str
            for_everyone: bool
        """
        message_id = payload.get("message_id")
        for_everyone = payload.get("for_everyone", False)

        if not message_id:
            return

        async with async_session_factory() as session:
            result = await session.execute(
                select(Message).where(Message.id == message_id)
            )
            message = result.scalar_one_or_none()

            if message is None:
                return

            chat_id = message.chat_id

            if for_everyone and message.author_id == connected_user.user_id:
                # Удаление для всех (только автор)
                message.is_deleted = True
                message.content_encrypted = None
                session.add(message)

                # Удаляем закреп если есть
                await session.execute(
                    delete(PinnedMessage).where(
                        PinnedMessage.message_id == message_id
                    )
                )
            else:
                # Удаление только для себя
                deleted_for = []
                if message.deleted_for_users:
                    try:
                        deleted_for = json.loads(message.deleted_for_users)
                    except json.JSONDecodeError:
                        deleted_for = []

                if connected_user.user_id not in deleted_for:
                    deleted_for.append(connected_user.user_id)
                    message.deleted_for_users = json.dumps(deleted_for)
                    session.add(message)

            await session.commit()

        if for_everyone and message.author_id == connected_user.user_id:
            # Уведомляем всех участников чата
            await self.manager.send_to_chat(
                chat_id=chat_id,
                event="message_deleted",
                data={
                    "message_id": message_id,
                    "chat_id": chat_id,
                    "for_everyone": True,
                },
            )
        else:
            # Уведомляем только этого пользователя
            await self.manager.send_to_user(
                connected_user.user_id,
                "message_deleted",
                {
                    "message_id": message_id,
                    "chat_id": chat_id,
                    "for_everyone": False,
                },
            )

    # ========================
    # Reactions
    # ========================

    async def handle_toggle_reaction(
            self,
            connected_user: ConnectedUser,
            payload: dict,
    ) -> None:
        """
        Добавить или убрать реакцию на сообщение.

        Payload:
            message_id: str
            emoji: str
        """
        message_id = payload.get("message_id")
        emoji = payload.get("emoji", "")

        if not message_id or not emoji:
            return

        async with async_session_factory() as session:
            # Проверяем существование сообщения
            msg_result = await session.execute(
                select(Message.chat_id).where(Message.id == message_id)
            )
            row = msg_result.first()
            if row is None:
                return
            chat_id = row[0]

            # Проверяем, есть ли уже такая реакция от этого пользователя
            existing = await session.execute(
                select(Reaction).where(
                    Reaction.message_id == message_id,
                    Reaction.user_id == connected_user.user_id,
                    Reaction.emoji == emoji,
                )
            )
            existing_reaction = existing.scalar_one_or_none()

            if existing_reaction:
                # Убираем реакцию
                await session.delete(existing_reaction)
            else:
                # Добавляем реакцию
                reaction = Reaction(
                    id=generate_uuid(),
                    message_id=message_id,
                    user_id=connected_user.user_id,
                    emoji=emoji,
                )
                session.add(reaction)

            await session.commit()

            # Собираем все реакции на сообщение
            reactions = await self._get_message_reactions(session, message_id)

        # Уведомляем чат
        await self.manager.send_to_chat(
            chat_id=chat_id,
            event="reaction_update",
            data={
                "message_id": message_id,
                "chat_id": chat_id,
                "reactions": reactions,
            },
        )

    async def _get_message_reactions(
            self,
            session: AsyncSession,
            message_id: str,
    ) -> list[dict]:
        """Собирает агрегированные реакции на сообщение."""
        result = await session.execute(
            select(Reaction)
            .where(Reaction.message_id == message_id)
            .options(selectinload(Reaction.user))
        )
        reactions_raw = result.scalars().all()

        # Группируем по emoji
        emoji_groups: dict[str, list[str]] = {}
        for r in reactions_raw:
            if r.emoji not in emoji_groups:
                emoji_groups[r.emoji] = []
            emoji_groups[r.emoji].append(r.user_id)

        return [
            {
                "emoji": emoji,
                "count": len(user_ids),
                "users": user_ids,
            }
            for emoji, user_ids in emoji_groups.items()
        ]

    # ========================
    # Typing
    # ========================

    async def handle_typing(
            self,
            connected_user: ConnectedUser,
            payload: dict,
    ) -> None:
        """
        Индикатор "печатает...".
        Клиент отправляет это событие при каждом вводе текста (с debounce 1 сек).

        Payload:
            chat_id: str
        """
        chat_id = payload.get("chat_id")
        if not chat_id:
            return

        await self.manager.set_typing(
            chat_id=chat_id,
            user_id=connected_user.user_id,
            username=connected_user.username,
            display_name=connected_user.display_name,
        )

    # ========================
    # Status
    # ========================

    async def handle_set_status(
            self,
            connected_user: ConnectedUser,
            payload: dict,
    ) -> None:
        """
        Смена статуса пользователя.

        Payload:
            status: str (online/away/do_not_disturb/invisible)
            custom_text: Optional[str]
        """
        new_status = payload.get("status")
        custom_text = payload.get("custom_text")

        allowed = {"online", "away", "do_not_disturb", "invisible"}
        if new_status not in allowed:
            return

        async with async_session_factory() as session:
            await session.execute(
                update(User)
                .where(User.id == connected_user.user_id)
                .values(
                    status=new_status,
                    custom_status_text=custom_text,
                    last_seen=utcnow(),
                )
            )
            await session.commit()

        await self.manager.broadcast_status_change(
            connected_user.user_id, new_status
        )

    # ========================
    # Pin / Unpin
    # ========================

    async def handle_pin_message(
            self,
            connected_user: ConnectedUser,
            payload: dict,
    ) -> None:
        """
        Закрепление сообщения.

        Payload:
            message_id: str
            chat_id: str
        """
        message_id = payload.get("message_id")
        chat_id = payload.get("chat_id")

        if not message_id or not chat_id:
            return

        async with async_session_factory() as session:
            # Проверяем что сообщение существует и принадлежит этому чату
            msg_result = await session.execute(
                select(Message).where(
                    Message.id == message_id,
                    Message.chat_id == chat_id,
                    Message.is_deleted == False,
                )
            )
            message = msg_result.scalar_one_or_none()
            if message is None:
                return

            # Проверяем что не закреплено уже
            existing = await session.execute(
                select(PinnedMessage).where(
                    PinnedMessage.message_id == message_id
                )
            )
            if existing.scalar_one_or_none() is not None:
                return

            pin = PinnedMessage(
                id=generate_uuid(),
                chat_id=chat_id,
                message_id=message_id,
                pinned_by_id=connected_user.user_id,
            )
            session.add(pin)
            await session.commit()

            # Формируем ответ
            msg_response = await self._build_message_response(
                session, message, connected_user.user_id
            )

        await self.manager.send_to_chat(
            chat_id=chat_id,
            event="pin_update",
            data={
                "chat_id": chat_id,
                "action": "pin",
                "message": msg_response,
                "pinned_by": connected_user.user_id,
            },
        )

    async def handle_unpin_message(
            self,
            connected_user: ConnectedUser,
            payload: dict,
    ) -> None:
        """
        Открепление сообщения.

        Payload:
            message_id: str
            chat_id: str
        """
        message_id = payload.get("message_id")
        chat_id = payload.get("chat_id")

        if not message_id or not chat_id:
            return

        async with async_session_factory() as session:
            result = await session.execute(
                delete(PinnedMessage).where(
                    PinnedMessage.message_id == message_id,
                    PinnedMessage.chat_id == chat_id,
                )
            )
            await session.commit()

        await self.manager.send_to_chat(
            chat_id=chat_id,
            event="pin_update",
            data={
                "chat_id": chat_id,
                "action": "unpin",
                "message_id": message_id,
            },
        )

    # ========================
    # Stickers
    # ========================

    async def handle_send_sticker(
            self,
            connected_user: ConnectedUser,
            payload: dict,
    ) -> None:
        """
        Отправка стикера.

        Payload:
            chat_id: str
            sticker_id: str
            reply_to_id: Optional[str]
        """
        chat_id = payload.get("chat_id")
        sticker_id = payload.get("sticker_id")
        reply_to_id = payload.get("reply_to_id")

        if not chat_id or not sticker_id:
            return

        async with async_session_factory() as session:
            # Проверяем стикер
            sticker_result = await session.execute(
                select(Sticker).where(Sticker.id == sticker_id)
            )
            sticker = sticker_result.scalar_one_or_none()
            if sticker is None:
                return

            # Проверяем членство
            is_member = await self._check_membership(
                session, chat_id, connected_user.user_id
            )
            if not is_member:
                return

            # Создаём сообщение-стикер
            message = Message(
                id=generate_uuid(),
                chat_id=chat_id,
                author_id=connected_user.user_id,
                message_type=MessageType.STICKER.value,
                reply_to_id=reply_to_id,
            )
            session.add(message)
            await session.flush()

            sticker_usage = StickerUsage(
                id=generate_uuid(),
                message_id=message.id,
                sticker_id=sticker_id,
            )
            session.add(sticker_usage)
            await session.commit()

            response = await self._build_message_response(
                session, message, connected_user.user_id
            )

        await self.manager.send_to_chat(
            chat_id=chat_id,
            event="new_message",
            data=response,
        )

    # ========================
    # Forward Messages
    # ========================

    async def handle_forward_messages(
            self,
            connected_user: ConnectedUser,
            payload: dict,
    ) -> None:
        """
        Пересылка одного или нескольких сообщений.

        Payload:
            message_ids: list[str]
            target_chat_id: str
        """
        message_ids = payload.get("message_ids", [])
        target_chat_id = payload.get("target_chat_id")

        if not message_ids or not target_chat_id:
            return

        async with async_session_factory() as session:
            # Проверяем членство в целевом чате
            is_member = await self._check_membership(
                session, target_chat_id, connected_user.user_id
            )
            if not is_member:
                return

            # Загружаем оригинальные сообщения
            result = await session.execute(
                select(Message)
                .where(Message.id.in_(message_ids), Message.is_deleted == False)
                .order_by(Message.created_at)
            )
            original_messages = result.scalars().all()

            forwarded_responses = []

            for orig_msg in original_messages:
                # Расшифровываем оригинальный контент
                original_content = ""
                if orig_msg.content_encrypted:
                    original_content = encryption_manager.decrypt(
                        orig_msg.content_encrypted
                    )

                # Шифруем заново для нового сообщения
                encrypted = encryption_manager.encrypt(original_content) if original_content else None

                new_message = Message(
                    id=generate_uuid(),
                    chat_id=target_chat_id,
                    author_id=connected_user.user_id,
                    message_type=orig_msg.message_type,
                    content_encrypted=encrypted,
                    forwarded_from_id=orig_msg.author_id,
                )
                session.add(new_message)
                await session.flush()

                response = await self._build_message_response(
                    session, new_message, connected_user.user_id
                )
                forwarded_responses.append(response)

            await session.commit()

        # Отправляем все пересланные сообщения
        for response in forwarded_responses:
            await self.manager.send_to_chat(
                chat_id=target_chat_id,
                event="new_message",
                data=response,
            )

    # ========================
    # Polls
    # ========================

    async def handle_create_poll(
            self,
            connected_user: ConnectedUser,
            payload: dict,
    ) -> None:
        """
        Создание опроса.

        Payload:
            chat_id: str
            question: str
            options: list[str]
            is_anonymous: bool
            is_multiple_choice: bool
        """
        chat_id = payload.get("chat_id")
        question = payload.get("question", "").strip()
        options = payload.get("options", [])
        is_anonymous = payload.get("is_anonymous", False)
        is_multiple_choice = payload.get("is_multiple_choice", False)

        if not chat_id or not question or len(options) < 2:
            return

        if len(options) > 10:
            return

        async with async_session_factory() as session:
            is_member = await self._check_membership(
                session, chat_id, connected_user.user_id
            )
            if not is_member:
                return

            # Создаём сообщение-опрос
            message = Message(
                id=generate_uuid(),
                chat_id=chat_id,
                author_id=connected_user.user_id,
                message_type=MessageType.POLL.value,
            )
            session.add(message)
            await session.flush()

            # Создаём опрос
            encrypted_question = encryption_manager.encrypt(question)
            poll = Poll(
                id=generate_uuid(),
                message_id=message.id,
                question_encrypted=encrypted_question,
                is_anonymous=is_anonymous,
                is_multiple_choice=is_multiple_choice,
            )
            session.add(poll)
            await session.flush()

            # Создаём варианты
            for i, option_text in enumerate(options):
                option = PollOption(
                    id=generate_uuid(),
                    poll_id=poll.id,
                    text_encrypted=encryption_manager.encrypt(option_text.strip()),
                    position=i,
                )
                session.add(option)

            await session.commit()

            response = await self._build_message_response(
                session, message, connected_user.user_id
            )

        await self.manager.send_to_chat(
            chat_id=chat_id,
            event="new_message",
            data=response,
        )

    async def handle_vote_poll(
            self,
            connected_user: ConnectedUser,
            payload: dict,
    ) -> None:
        """
        Голосование в опросе.

        Payload:
            poll_id: str
            option_ids: list[str]
        """
        poll_id = payload.get("poll_id")
        option_ids = payload.get("option_ids", [])

        if not poll_id or not option_ids:
            return

        async with async_session_factory() as session:
            # Загружаем опрос
            poll_result = await session.execute(
                select(Poll)
                .where(Poll.id == poll_id, Poll.is_closed == False)
                .options(selectinload(Poll.options).selectinload(PollOption.votes))
            )
            poll = poll_result.scalar_one_or_none()
            if poll is None:
                return

            # Получаем message и chat_id
            msg_result = await session.execute(
                select(Message.chat_id).where(Message.id == poll.message_id)
            )
            row = msg_result.first()
            if row is None:
                return
            chat_id = row[0]

            if not poll.is_multiple_choice:
                # Одиночный выбор — удаляем предыдущие голоса
                for option in poll.options:
                    for vote in option.votes:
                        if vote.user_id == connected_user.user_id:
                            await session.delete(vote)

                # Добавляем новый голос (только первый option_id)
                if option_ids:
                    vote = PollVote(
                        id=generate_uuid(),
                        option_id=option_ids[0],
                        user_id=connected_user.user_id,
                    )
                    session.add(vote)
            else:
                # Множественный выбор — переключаем голоса
                for option in poll.options:
                    user_voted = any(
                        v.user_id == connected_user.user_id
                        for v in option.votes
                    )

                    if option.id in option_ids and not user_voted:
                        vote = PollVote(
                            id=generate_uuid(),
                            option_id=option.id,
                            user_id=connected_user.user_id,
                        )
                        session.add(vote)
                    elif option.id not in option_ids and user_voted:
                        for v in option.votes:
                            if v.user_id == connected_user.user_id:
                                await session.delete(v)

            await session.commit()

            # Собираем обновлённый опрос
            poll_response = await self._build_poll_response(
                session, poll_id, connected_user.user_id
            )

        await self.manager.send_to_chat(
            chat_id=chat_id,
            event="poll_update",
            data={
                "poll_id": poll_id,
                "message_id": poll.message_id,
                "chat_id": chat_id,
                "poll": poll_response,
            },
        )

    # ========================
    # Mark Read
    # ========================

    async def handle_mark_read(
            self,
            connected_user: ConnectedUser,
            payload: dict,
    ) -> None:
        """
        Отмечает сообщения как прочитанные.

        Payload:
            chat_id: str
            last_message_id: str
        """
        chat_id = payload.get("chat_id")
        last_message_id = payload.get("last_message_id")

        if not chat_id or not last_message_id:
            return

        async with async_session_factory() as session:
            # Обновляем или создаём ReadState
            result = await session.execute(
                select(ReadState).where(
                    ReadState.chat_id == chat_id,
                    ReadState.user_id == connected_user.user_id,
                )
            )
            read_state = result.scalar_one_or_none()

            if read_state:
                read_state.last_read_message_id = last_message_id
                read_state.last_read_at = utcnow()
            else:
                read_state = ReadState(
                    id=generate_uuid(),
                    chat_id=chat_id,
                    user_id=connected_user.user_id,
                    last_read_message_id=last_message_id,
                )
                session.add(read_state)

            await session.commit()

    # ========================
    # Helper Methods
    # ========================

    async def _check_membership(
            self,
            session: AsyncSession,
            chat_id: str,
            user_id: str,
    ) -> bool:
        """Проверяет, является ли пользователь участником чата."""
        result = await session.execute(
            select(ChatMember).where(
                ChatMember.chat_id == chat_id,
                ChatMember.user_id == user_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def _build_message_response(
            self,
            session: AsyncSession,
            message: Message,
            requesting_user_id: str,
    ) -> dict:
        """
        Формирует полный ответ сообщения для отправки клиенту.
        Расшифровывает контент, загружает связи.
        """
        # Загружаем автора
        author_result = await session.execute(
            select(User).where(User.id == message.author_id)
        )
        author = author_result.scalar_one()

        author_response = {
            "id": author.id,
            "username": author.username,
            "display_name": author.display_name,
            "nick_color": author.nick_color,
            "avatar_path": author.avatar_path,
            "status": author.status,
        }

        # Расшифровываем контент
        content = None
        if message.content_encrypted:
            content = encryption_manager.decrypt(message.content_encrypted)

        # Reply info
        reply_info = None
        if message.reply_to_id:
            reply_result = await session.execute(
                select(Message).where(Message.id == message.reply_to_id)
            )
            reply_msg = reply_result.scalar_one_or_none()
            if reply_msg:
                reply_author_result = await session.execute(
                    select(User).where(User.id == reply_msg.author_id)
                )
                reply_author = reply_author_result.scalar_one()

                reply_content = None
                if reply_msg.is_deleted:
                    reply_content = None
                elif reply_msg.content_encrypted:
                    reply_content = encryption_manager.decrypt(
                        reply_msg.content_encrypted
                    )
                    # Обрезаем для превью
                    if reply_content and len(reply_content) > 100:
                        reply_content = reply_content[:100] + "..."

                reply_info = {
                    "id": reply_msg.id,
                    "author": {
                        "id": reply_author.id,
                        "username": reply_author.username,
                        "display_name": reply_author.display_name,
                        "nick_color": reply_author.nick_color,
                    },
                    "content": reply_content,
                    "is_deleted": reply_msg.is_deleted,
                    "message_type": reply_msg.message_type,
                }

        # Forwarded from
        forwarded_from = None
        if message.forwarded_from_id:
            fwd_result = await session.execute(
                select(User).where(User.id == message.forwarded_from_id)
            )
            fwd_user = fwd_result.scalar_one_or_none()
            if fwd_user:
                forwarded_from = {
                    "id": fwd_user.id,
                    "username": fwd_user.username,
                    "display_name": fwd_user.display_name,
                    "nick_color": fwd_user.nick_color,
                }

        # Реакции
        reactions = await self._get_message_reactions(session, message.id)

        # Файл
        file_attachment = None
        file_result = await session.execute(
            select(FileAttachment).where(FileAttachment.message_id == message.id)
        )
        file_obj = file_result.scalar_one_or_none()
        if file_obj:
            file_attachment = {
                "id": file_obj.id,
                "original_filename": file_obj.original_filename,
                "file_size": file_obj.file_size,
                "mime_type": file_obj.mime_type,
                "has_thumbnail": file_obj.has_thumbnail,
                "image_width": file_obj.image_width,
                "image_height": file_obj.image_height,
                "video_duration": file_obj.video_duration,
                "upload_complete": file_obj.upload_complete,
            }

        # Опрос
        poll = None
        if message.message_type == MessageType.POLL.value:
            poll_result = await session.execute(
                select(Poll).where(Poll.message_id == message.id)
            )
            poll_obj = poll_result.scalar_one_or_none()
            if poll_obj:
                poll = await self._build_poll_response(
                    session, poll_obj.id, requesting_user_id
                )

        # Стикер
        sticker = None
        sticker_result = await session.execute(
            select(StickerUsage)
            .where(StickerUsage.message_id == message.id)
            .options(selectinload(StickerUsage.sticker).selectinload(Sticker.pack))
        )
        sticker_usage = sticker_result.scalar_one_or_none()
        if sticker_usage and sticker_usage.sticker:
            s = sticker_usage.sticker
            sticker = {
                "id": s.id,
                "pack_id": s.pack_id,
                "pack_name": s.pack.name if s.pack else "",
                "filename": s.filename,
                "is_animated": s.is_animated,
                "mime_type": s.mime_type,
                "width": s.width,
                "height": s.height,
            }

        # Закреплено?
        pin_result = await session.execute(
            select(PinnedMessage).where(PinnedMessage.message_id == message.id)
        )
        is_pinned = pin_result.scalar_one_or_none() is not None

        return {
            "id": message.id,
            "chat_id": message.chat_id,
            "author": author_response,
            "message_type": message.message_type,
            "content": content,
            "reply_to": reply_info,
            "forwarded_from": forwarded_from,
            "is_edited": message.is_edited,
            "is_deleted": message.is_deleted,
            "reactions": reactions,
            "file_attachment": file_attachment,
            "poll": poll,
            "sticker": sticker,
            "pinned": is_pinned,
            "created_at": message.created_at.isoformat() if message.created_at else None,
        }

    async def _build_poll_response(
            self,
            session: AsyncSession,
            poll_id: str,
            requesting_user_id: str,
    ) -> dict:
        """Формирует ответ опроса с подсчётом голосов."""
        result = await session.execute(
            select(Poll)
            .where(Poll.id == poll_id)
            .options(
                selectinload(Poll.options)
                .selectinload(PollOption.votes)
                .selectinload(PollVote.user)
            )
        )
        poll = result.scalar_one_or_none()
        if poll is None:
            return {}

        question = encryption_manager.decrypt(poll.question_encrypted)

        # Считаем общее количество голосов
        total_votes = sum(len(opt.votes) for opt in poll.options)

        options = []
        my_votes = []
        for opt in poll.options:
            text = encryption_manager.decrypt(opt.text_encrypted)
            vote_count = len(opt.votes)
            percentage = (vote_count / total_votes * 100) if total_votes > 0 else 0

            voters = []
            for vote in opt.votes:
                if vote.user_id == requesting_user_id:
                    my_votes.append(opt.id)

                if not poll.is_anonymous and vote.user:
                    voters.append({
                        "id": vote.user.id,
                        "username": vote.user.username,
                        "display_name": vote.user.display_name,
                        "nick_color": vote.user.nick_color,
                    })

            options.append({
                "id": opt.id,
                "text": text,
                "vote_count": vote_count,
                "percentage": round(percentage, 1),
                "voters": voters,
            })

        return {
            "id": poll.id,
            "question": question,
            "options": options,
            "is_anonymous": poll.is_anonymous,
            "is_multiple_choice": poll.is_multiple_choice,
            "is_closed": poll.is_closed,
            "total_votes": total_votes,
            "my_votes": my_votes,
        }


# Глобальный экземпляр
from server.websocket.manager import connection_manager
ws_handler = WebSocketHandler(manager=connection_manager)
