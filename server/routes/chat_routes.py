"""
Lantern v2 — Chat Routes
REST-эндпоинты для управления чатами: список, создание, история, поиск, закреплённые.
"""

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from server.database import (
    get_session, User, Chat, ChatMember, Message, MessageType,
    ChatType, PinnedMessage, ReadState, Reaction, FileAttachment,
    Poll, PollOption, PollVote, Sticker, StickerUsage, StickerPack,
    generate_uuid, utcnow
)
from server.models import (
    ChatResponse, UserResponse, MessageResponse, MessageReplyInfo,
    CreateDirectChatRequest, PinnedMessageResponse, StickerPackResponse,
    StickerResponse
)
from server.auth import get_current_user
from server.encryption import encryption_manager
from server.config import config


router = APIRouter(prefix="/api/chats", tags=["chats"])


# ========================
# Chat List
# ========================

@router.get("", response_model=list[ChatResponse])
async def get_chats(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ChatResponse]:
    """
    Получить список всех чатов текущего пользователя.
    Включает последнее сообщение и количество непрочитанных.
    """
    # Загружаем чаты пользователя
    memberships_result = await session.execute(
        select(ChatMember.chat_id).where(ChatMember.user_id == current_user.id)
    )
    chat_ids = [row[0] for row in memberships_result.fetchall()]

    if not chat_ids:
        return []

    # Загружаем чаты с участниками
    chats_result = await session.execute(
        select(Chat)
        .where(Chat.id.in_(chat_ids))
        .options(selectinload(Chat.members).selectinload(ChatMember.user))
    )
    chats = chats_result.scalars().all()

    result = []
    for chat in chats:
        # Последнее сообщение
        last_msg_result = await session.execute(
            select(Message)
            .where(
                Message.chat_id == chat.id,
                Message.is_deleted == False,
            )
            .order_by(desc(Message.created_at))
            .limit(1)
        )
        last_message_obj = last_msg_result.scalar_one_or_none()

        last_message = None
        if last_message_obj:
            # Проверяем что не удалено для текущего пользователя
            is_hidden = False
            if last_message_obj.deleted_for_users:
                try:
                    deleted_for = json.loads(last_message_obj.deleted_for_users)
                    is_hidden = current_user.id in deleted_for
                except json.JSONDecodeError:
                    pass

            if not is_hidden:
                # Загружаем автора последнего сообщения
                author_result = await session.execute(
                    select(User).where(User.id == last_message_obj.author_id)
                )
                last_author = author_result.scalar_one()

                content = None
                if last_message_obj.content_encrypted:
                    content = encryption_manager.decrypt(last_message_obj.content_encrypted)
                    if content and len(content) > 50:
                        content = content[:50] + "..."

                last_message = {
                    "id": last_message_obj.id,
                    "chat_id": chat.id,
                    "author": {
                        "id": last_author.id,
                        "username": last_author.username,
                        "display_name": last_author.display_name,
                        "nick_color": last_author.nick_color,
                        "avatar_path": last_author.avatar_path,
                        "status": last_author.status,
                    },
                    "message_type": last_message_obj.message_type,
                    "content": content,
                    "is_edited": last_message_obj.is_edited,
                    "is_deleted": last_message_obj.is_deleted,
                    "created_at": last_message_obj.created_at.isoformat(),
                    "reactions": [],
                    "file_attachment": None,
                    "poll": None,
                    "sticker": None,
                    "reply_to": None,
                    "forwarded_from": None,
                    "pinned": False,
                }

        # Непрочитанные
        unread_count = await _get_unread_count(session, chat.id, current_user.id)

        # Закреплённые
        pinned_count_result = await session.execute(
            select(func.count()).select_from(PinnedMessage).where(
                PinnedMessage.chat_id == chat.id
            )
        )
        pinned_count = pinned_count_result.scalar() or 0

        # Участники
        members = [
            UserResponse(
                id=m.user.id,
                username=m.user.username,
                display_name=m.user.display_name,
                nick_color=m.user.nick_color,
                avatar_path=m.user.avatar_path,
                status=m.user.status,
                custom_status_text=m.user.custom_status_text,
                last_seen=m.user.last_seen,
            )
            for m in chat.members
        ]

        # Имя чата: для direct — имя собеседника
        chat_name = chat.name
        if chat.chat_type == ChatType.DIRECT.value:
            for m in chat.members:
                if m.user.id != current_user.id:
                    chat_name = m.user.display_name
                    break

        result.append(ChatResponse(
            id=chat.id,
            chat_type=chat.chat_type,
            name=chat_name,
            members=members,
            last_message=last_message,
            unread_count=unread_count,
            pinned_count=pinned_count,
            created_at=chat.created_at,
        ))

    # Сортируем: чаты с последними сообщениями первыми
    result.sort(
        key=lambda c: c.last_message["created_at"] if c.last_message else "0",
        reverse=True,
    )

    return result


# ========================
# Create Direct Chat
# ========================

@router.post("/direct", response_model=ChatResponse, status_code=status.HTTP_201_CREATED)
async def create_direct_chat(
    request: CreateDirectChatRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ChatResponse:
    """
    Создать личный чат (1-на-1).
    Если чат между этими пользователями уже существует — возвращает его.
    """
    if request.target_user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя создать чат с самим собой"
        )

    # Проверяем существование целевого пользователя
    target_result = await session.execute(
        select(User).where(User.id == request.target_user_id)
    )
    target_user = target_result.scalar_one_or_none()
    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден"
        )

    # Ищем существующий direct чат между этими пользователями
    existing_chat = await _find_direct_chat(session, current_user.id, request.target_user_id)
    if existing_chat:
        return await _build_chat_response(session, existing_chat, current_user)

    # Создаём новый direct чат
    chat = Chat(
        id=generate_uuid(),
        chat_type=ChatType.DIRECT.value,
        name=None,
    )
    session.add(chat)
    await session.flush()

    # Добавляем обоих участников
    for uid in [current_user.id, request.target_user_id]:
        member = ChatMember(
            id=generate_uuid(),
            chat_id=chat.id,
            user_id=uid,
        )
        session.add(member)

    await session.commit()

    # Перезагружаем с участниками
    chat_result = await session.execute(
        select(Chat)
        .where(Chat.id == chat.id)
        .options(selectinload(Chat.members).selectinload(ChatMember.user))
    )
    chat = chat_result.scalar_one()

    return await _build_chat_response(session, chat, current_user)


# ========================
# Message History
# ========================

@router.get("/{chat_id}/messages")
async def get_messages(
    chat_id: str,
    before: Optional[str] = Query(None, description="ID сообщения для пагинации (загрузить ДО него)"),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """
    Получить историю сообщений чата.
    Поддерживает пагинацию: передайте before=message_id для загрузки старых сообщений.
    """
    # Проверяем членство
    is_member = await _check_membership(session, chat_id, current_user.id)
    if not is_member:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Вы не участник этого чата")

    query = (
        select(Message)
        .where(
            Message.chat_id == chat_id,
        )
    )

    # Пагинация: если передан before, загружаем сообщения до него
    if before:
        before_msg = await session.execute(
            select(Message.created_at).where(Message.id == before)
        )
        before_row = before_msg.first()
        if before_row:
            query = query.where(Message.created_at < before_row[0])

    query = query.order_by(desc(Message.created_at)).limit(limit)

    result = await session.execute(query)
    messages = result.scalars().all()

    # Разворачиваем в хронологический порядок
    messages = list(reversed(messages))

    responses = []
    for msg in messages:
        # Пропускаем удалённые для текущего пользователя
        if msg.deleted_for_users:
            try:
                deleted_for = json.loads(msg.deleted_for_users)
                if current_user.id in deleted_for:
                    continue
            except json.JSONDecodeError:
                pass

        response = await _build_full_message_response(session, msg, current_user.id)
        responses.append(response)

    return responses


# ========================
# Search Messages
# ========================

@router.get("/{chat_id}/search")
async def search_messages(
    chat_id: str,
    q: str = Query(..., min_length=1, max_length=256, description="Поисковый запрос"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Полнотекстовый поиск по сообщениям в чате.
    Расшифровывает сообщения и ищет по содержимому.
    """
    is_member = await _check_membership(session, chat_id, current_user.id)
    if not is_member:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Вы не участник этого чата")

    # Загружаем все текстовые сообщения чата
    # (Для SQLite без FTS5 — делаем поиск на стороне сервера после расшифровки)
    result = await session.execute(
        select(Message)
        .where(
            Message.chat_id == chat_id,
            Message.is_deleted == False,
            Message.message_type == MessageType.TEXT.value,
            Message.content_encrypted.isnot(None),
        )
        .order_by(desc(Message.created_at))
    )
    all_messages = result.scalars().all()

    # Расшифровываем и фильтруем
    query_lower = q.lower()
    matched = []
    for msg in all_messages:
        content = encryption_manager.decrypt(msg.content_encrypted)
        if content and query_lower in content.lower():
            matched.append(msg)

    # Пагинация
    total = len(matched)
    start = (page - 1) * per_page
    end = start + per_page
    page_messages = matched[start:end]

    responses = []
    for msg in page_messages:
        response = await _build_full_message_response(session, msg, current_user.id)
        responses.append(response)

    return {
        "messages": responses,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page if total > 0 else 0,
    }


# ========================
# Pinned Messages
# ========================

@router.get("/{chat_id}/pinned")
async def get_pinned_messages(
    chat_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Получить все закреплённые сообщения в чате."""
    is_member = await _check_membership(session, chat_id, current_user.id)
    if not is_member:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Вы не участник этого чата")

    result = await session.execute(
        select(PinnedMessage)
        .where(PinnedMessage.chat_id == chat_id)
        .options(
            selectinload(PinnedMessage.message),
            selectinload(PinnedMessage.pinned_by),
        )
        .order_by(desc(PinnedMessage.pinned_at))
    )
    pinned = result.scalars().all()

    responses = []
    for pin in pinned:
        msg_response = await _build_full_message_response(
            session, pin.message, current_user.id
        )
        responses.append({
            "id": pin.id,
            "message": msg_response,
            "pinned_by": {
                "id": pin.pinned_by.id,
                "username": pin.pinned_by.username,
                "display_name": pin.pinned_by.display_name,
                "nick_color": pin.pinned_by.nick_color,
            },
            "pinned_at": pin.pinned_at.isoformat(),
        })

    return responses


# ========================
# Sticker Packs
# ========================

@router.get("/stickers/packs", response_model=list[StickerPackResponse])
async def get_sticker_packs(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[StickerPackResponse]:
    """Получить все доступные наборы стикеров."""
    result = await session.execute(
        select(StickerPack)
        .options(selectinload(StickerPack.stickers))
        .order_by(StickerPack.name)
    )
    packs = result.scalars().all()

    responses = []
    for pack in packs:
        stickers = [
            StickerResponse(
                id=s.id,
                pack_id=s.pack_id,
                pack_name=pack.name,
                filename=s.filename,
                is_animated=s.is_animated,
                mime_type=s.mime_type,
                width=s.width,
                height=s.height,
            )
            for s in pack.stickers
        ]
        responses.append(StickerPackResponse(
            id=pack.id,
            name=pack.name,
            stickers=stickers,
            cover_sticker=stickers[0] if stickers else None,
        ))

    return responses


# ========================
# Unread Count
# ========================

@router.post("/{chat_id}/mark-read")
async def mark_chat_read(
    chat_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Отметить все сообщения в чате как прочитанные."""
    # Получаем последнее сообщение
    last_msg_result = await session.execute(
        select(Message)
        .where(Message.chat_id == chat_id, Message.is_deleted == False)
        .order_by(desc(Message.created_at))
        .limit(1)
    )
    last_msg = last_msg_result.scalar_one_or_none()

    if last_msg is None:
        return {"status": "ok"}

    # Обновляем ReadState
    rs_result = await session.execute(
        select(ReadState).where(
            ReadState.chat_id == chat_id,
            ReadState.user_id == current_user.id,
        )
    )
    read_state = rs_result.scalar_one_or_none()

    if read_state:
        read_state.last_read_message_id = last_msg.id
        read_state.last_read_at = utcnow()
    else:
        read_state = ReadState(
            id=generate_uuid(),
            chat_id=chat_id,
            user_id=current_user.id,
            last_read_message_id=last_msg.id,
        )
        session.add(read_state)

    await session.commit()
    return {"status": "ok"}


# ========================
# Helper Functions
# ========================

async def _find_direct_chat(
    session: AsyncSession,
    user1_id: str,
    user2_id: str,
) -> Optional[Chat]:
    """Ищет существующий direct чат между двумя пользователями."""
    # Находим чаты, где оба пользователя — участники
    result = await session.execute(
        select(Chat)
        .join(ChatMember, Chat.id == ChatMember.chat_id)
        .where(
            Chat.chat_type == ChatType.DIRECT.value,
            ChatMember.user_id.in_([user1_id, user2_id]),
        )
        .options(selectinload(Chat.members).selectinload(ChatMember.user))
    )
    chats = result.scalars().unique().all()

    for chat in chats:
        member_ids = {m.user_id for m in chat.members}
        if user1_id in member_ids and user2_id in member_ids:
            return chat

    return None


async def _check_membership(
    session: AsyncSession,
    chat_id: str,
    user_id: str,
) -> bool:
    """Проверяет членство пользователя в чате."""
    result = await session.execute(
        select(ChatMember).where(
            ChatMember.chat_id == chat_id,
            ChatMember.user_id == user_id,
        )
    )
    return result.scalar_one_or_none() is not None


async def _get_unread_count(
    session: AsyncSession,
    chat_id: str,
    user_id: str,
) -> int:
    """Подсчитывает количество непрочитанных сообщений."""
    # Получаем last_read
    rs_result = await session.execute(
        select(ReadState).where(
            ReadState.chat_id == chat_id,
            ReadState.user_id == user_id,
        )
    )
    read_state = rs_result.scalar_one_or_none()

    query = select(func.count()).select_from(Message).where(
        Message.chat_id == chat_id,
        Message.is_deleted == False,
        Message.author_id != user_id,  # Свои сообщения не считаем
    )

    if read_state and read_state.last_read_message_id:
        # Получаем время последнего прочитанного
        last_read_result = await session.execute(
            select(Message.created_at).where(Message.id == read_state.last_read_message_id)
        )
        last_read_row = last_read_result.first()
        if last_read_row:
            query = query.where(Message.created_at > last_read_row[0])

    result = await session.execute(query)
    return result.scalar() or 0


async def _build_chat_response(
    session: AsyncSession,
    chat: Chat,
    current_user: User,
) -> ChatResponse:
    """Формирует ChatResponse из объекта Chat."""
    members = [
        UserResponse(
            id=m.user.id,
            username=m.user.username,
            display_name=m.user.display_name,
            nick_color=m.user.nick_color,
            avatar_path=m.user.avatar_path,
            status=m.user.status,
            custom_status_text=m.user.custom_status_text,
            last_seen=m.user.last_seen,
        )
        for m in chat.members
    ]

    chat_name = chat.name
    if chat.chat_type == ChatType.DIRECT.value:
        for m in chat.members:
            if m.user.id != current_user.id:
                chat_name = m.user.display_name
                break

    unread = await _get_unread_count(session, chat.id, current_user.id)

    return ChatResponse(
        id=chat.id,
        chat_type=chat.chat_type,
        name=chat_name,
        members=members,
        last_message=None,
        unread_count=unread,
        pinned_count=0,
        created_at=chat.created_at,
    )


async def _build_full_message_response(
    session: AsyncSession,
    message: Message,
    requesting_user_id: str,
) -> dict:
    """Формирует полный ответ сообщения с расшифровкой и всеми связями."""
    # Автор
    author_result = await session.execute(
        select(User).where(User.id == message.author_id)
    )
    author = author_result.scalar_one()

    author_data = {
        "id": author.id,
        "username": author.username,
        "display_name": author.display_name,
        "nick_color": author.nick_color,
        "avatar_path": author.avatar_path,
        "status": author.status,
    }

    # Контент
    content = None
    if message.content_encrypted and not message.is_deleted:
        content = encryption_manager.decrypt(message.content_encrypted)

    # Reply
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
                reply_content = encryption_manager.decrypt(reply_msg.content_encrypted)
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

    # Forwarded
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
    reactions_result = await session.execute(
        select(Reaction).where(Reaction.message_id == message.id)
    )
    reactions_raw = reactions_result.scalars().all()
    emoji_groups: dict[str, list[str]] = {}
    for r in reactions_raw:
        if r.emoji not in emoji_groups:
            emoji_groups[r.emoji] = []
        emoji_groups[r.emoji].append(r.user_id)
    reactions = [
        {"emoji": e, "count": len(u), "users": u}
        for e, u in emoji_groups.items()
    ]

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
            select(Poll)
            .where(Poll.message_id == message.id)
            .options(
                selectinload(Poll.options)
                .selectinload(PollOption.votes)
                .selectinload(PollVote.user)
            )
        )
        poll_obj = poll_result.scalar_one_or_none()
        if poll_obj:
            question = encryption_manager.decrypt(poll_obj.question_encrypted)
            total_votes = sum(len(opt.votes) for opt in poll_obj.options)
            my_votes = []
            options = []
            for opt in poll_obj.options:
                text = encryption_manager.decrypt(opt.text_encrypted)
                vote_count = len(opt.votes)
                pct = (vote_count / total_votes * 100) if total_votes > 0 else 0
                voters = []
                for v in opt.votes:
                    if v.user_id == requesting_user_id:
                        my_votes.append(opt.id)
                    if not poll_obj.is_anonymous and v.user:
                        voters.append({
                            "id": v.user.id,
                            "username": v.user.username,
                            "display_name": v.user.display_name,
                            "nick_color": v.user.nick_color,
                        })
                options.append({
                    "id": opt.id,
                    "text": text,
                    "vote_count": vote_count,
                    "percentage": round(pct, 1),
                    "voters": voters,
                })
            poll = {
                "id": poll_obj.id,
                "question": question,
                "options": options,
                "is_anonymous": poll_obj.is_anonymous,
                "is_multiple_choice": poll_obj.is_multiple_choice,
                "is_closed": poll_obj.is_closed,
                "total_votes": total_votes,
                "my_votes": my_votes,
            }

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
        "author": author_data,
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