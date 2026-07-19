"""
Lantern v2 — Database Models (SQLAlchemy Async)
Все таблицы базы данных.
Поддерживает: пользователей, чаты, сообщения, реакции, опросы,
закреплённые сообщения, файлы, стикеры.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    String, Integer, BigInteger, Float, Boolean, Text, DateTime,
    ForeignKey, UniqueConstraint, Index, Enum as SAEnum, JSON
)
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, mapped_column, relationship
)
from sqlalchemy.ext.asyncio import (
    AsyncSession, create_async_engine, async_sessionmaker, AsyncAttrs
)

from server.config import config

import enum


# ========================
# Enums
# ========================

class UserStatus(str, enum.Enum):
    """Статусы пользователя."""
    ONLINE = "online"
    AWAY = "away"
    DO_NOT_DISTURB = "do_not_disturb"
    INVISIBLE = "invisible"
    OFFLINE = "offline"


class ChatType(str, enum.Enum):
    """Типы чатов."""
    GENERAL = "general"   # Общий чат
    DIRECT = "direct"     # Личный (1-на-1)


class MessageType(str, enum.Enum):
    """Типы сообщений."""
    TEXT = "text"
    FILE = "file"
    STICKER = "sticker"
    POLL = "poll"
    SYSTEM = "system"     # "Alice присоединился" и т.д.


# ========================
# Base
# ========================

class Base(AsyncAttrs, DeclarativeBase):
    """Базовый класс для всех моделей."""
    pass


# ========================
# Helpers
# ========================

def generate_uuid() -> str:
    """Генерирует UUID4 строку."""
    return str(uuid.uuid4())


def utcnow() -> datetime:
    """Текущее UTC время."""
    return datetime.now(timezone.utc)


# ========================
# Models
# ========================

class User(Base):
    """Пользователь мессенджера."""
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    nick_color: Mapped[str] = mapped_column(String(7), nullable=False, default="#cba6f7")  # Hex color
    avatar_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=UserStatus.OFFLINE.value
    )
    custom_status_text: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Relationships
    sent_messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="author", cascade="all, delete-orphan"
    )
    reactions: Mapped[list["Reaction"]] = relationship(
        "Reaction", back_populates="user", cascade="all, delete-orphan"
    )
    poll_votes: Mapped[list["PollVote"]] = relationship(
        "PollVote", back_populates="user", cascade="all, delete-orphan"
    )
    chat_memberships: Mapped[list["ChatMember"]] = relationship(
        "ChatMember", back_populates="user", cascade="all, delete-orphan"
    )
    read_states: Mapped[list["ReadState"]] = relationship(
        "ReadState", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User {self.username} ({self.display_name})>"


class Chat(Base):
    """Чат (общий или личный)."""
    __tablename__ = "chats"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    chat_type: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)  # Для general
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Relationships
    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="chat", cascade="all, delete-orphan",
        order_by="Message.created_at"
    )
    members: Mapped[list["ChatMember"]] = relationship(
        "ChatMember", back_populates="chat", cascade="all, delete-orphan"
    )
    pinned_messages: Mapped[list["PinnedMessage"]] = relationship(
        "PinnedMessage", back_populates="chat", cascade="all, delete-orphan"
    )
    read_states: Mapped[list["ReadState"]] = relationship(
        "ReadState", back_populates="chat", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Chat {self.chat_type}: {self.name or self.id}>"


class ChatMember(Base):
    """Связь пользователь-чат (membership)."""
    __tablename__ = "chat_members"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    chat_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Relationships
    chat: Mapped["Chat"] = relationship("Chat", back_populates="members")
    user: Mapped["User"] = relationship("User", back_populates="chat_memberships")

    __table_args__ = (
        UniqueConstraint("chat_id", "user_id", name="uq_chat_member"),
    )


class Message(Base):
    """Сообщение в чате."""
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    chat_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    message_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default=MessageType.TEXT.value
    )

    # Контент (зашифрован Fernet)
    content_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Ответ на сообщение
    reply_to_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )

    # Пересылка
    forwarded_from_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Редактирование
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False)

    # Удаление
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_for_users: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True  # JSON-список user_id, для кого удалено
    )

    # Временные метки
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    chat: Mapped["Chat"] = relationship("Chat", back_populates="messages")
    author: Mapped["User"] = relationship("User", back_populates="sent_messages", foreign_keys=[author_id])
    forwarded_from: Mapped[Optional["User"]] = relationship("User", foreign_keys=[forwarded_from_id])
    reply_to: Mapped[Optional["Message"]] = relationship(
        "Message", remote_side="Message.id", foreign_keys=[reply_to_id]
    )
    reactions: Mapped[list["Reaction"]] = relationship(
        "Reaction", back_populates="message", cascade="all, delete-orphan"
    )
    file_attachment: Mapped[Optional["FileAttachment"]] = relationship(
        "FileAttachment", back_populates="message", uselist=False, cascade="all, delete-orphan"
    )
    poll: Mapped[Optional["Poll"]] = relationship(
        "Poll", back_populates="message", uselist=False, cascade="all, delete-orphan"
    )
    sticker: Mapped[Optional["StickerUsage"]] = relationship(
        "StickerUsage", back_populates="message", uselist=False, cascade="all, delete-orphan"
    )
    pinned_entry: Mapped[Optional["PinnedMessage"]] = relationship(
        "PinnedMessage", back_populates="message", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_messages_chat_created", "chat_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Message {self.id[:8]} in {self.chat_id[:8]} by {self.author_id[:8]}>"


class FileAttachment(Base):
    """Прикреплённый файл к сообщению."""
    __tablename__ = "file_attachments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    message_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(512), nullable=False)  # UUID-имя на диске
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False, default="application/octet-stream")
    has_thumbnail: Mapped[bool] = mapped_column(Boolean, default=False)
    thumbnail_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # Для изображений
    image_width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    image_height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Для видео
    video_duration: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Чанковая загрузка
    upload_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    total_chunks: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    uploaded_chunks: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Relationships
    message: Mapped["Message"] = relationship("Message", back_populates="file_attachment")

    def __repr__(self) -> str:
        return f"<File {self.original_filename} ({self.file_size} bytes)>"


class Reaction(Base):
    """Реакция на сообщение."""
    __tablename__ = "reactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    message_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    emoji: Mapped[str] = mapped_column(String(32), nullable=False)  # Unicode emoji
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Relationships
    message: Mapped["Message"] = relationship("Message", back_populates="reactions")
    user: Mapped["User"] = relationship("User", back_populates="reactions")

    __table_args__ = (
        UniqueConstraint("message_id", "user_id", "emoji", name="uq_reaction"),
    )


class Poll(Base):
    """Опрос, прикреплённый к сообщению."""
    __tablename__ = "polls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    message_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    question_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False)
    is_multiple_choice: Mapped[bool] = mapped_column(Boolean, default=False)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Relationships
    message: Mapped["Message"] = relationship("Message", back_populates="poll")
    options: Mapped[list["PollOption"]] = relationship(
        "PollOption", back_populates="poll", cascade="all, delete-orphan",
        order_by="PollOption.position"
    )


class PollOption(Base):
    """Вариант ответа в опросе."""
    __tablename__ = "poll_options"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    poll_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("polls.id", ondelete="CASCADE"), nullable=False
    )
    text_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Relationships
    poll: Mapped["Poll"] = relationship("Poll", back_populates="options")
    votes: Mapped[list["PollVote"]] = relationship(
        "PollVote", back_populates="option", cascade="all, delete-orphan"
    )


class PollVote(Base):
    """Голос пользователя в опросе."""
    __tablename__ = "poll_votes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    option_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("poll_options.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Relationships
    option: Mapped["PollOption"] = relationship("PollOption", back_populates="votes")
    user: Mapped["User"] = relationship("User", back_populates="poll_votes")

    __table_args__ = (
        UniqueConstraint("option_id", "user_id", name="uq_poll_vote"),
    )


class PinnedMessage(Base):
    """Закреплённое сообщение в чате."""
    __tablename__ = "pinned_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    chat_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True
    )
    message_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    pinned_by_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    pinned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Relationships
    chat: Mapped["Chat"] = relationship("Chat", back_populates="pinned_messages")
    message: Mapped["Message"] = relationship("Message", back_populates="pinned_entry")
    pinned_by: Mapped["User"] = relationship("User")


class StickerPack(Base):
    """Набор стикеров."""
    __tablename__ = "sticker_packs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    directory_name: Mapped[str] = mapped_column(String(256), nullable=False)
    cover_sticker_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Relationships
    stickers: Mapped[list["Sticker"]] = relationship(
        "Sticker", back_populates="pack", cascade="all, delete-orphan",
        order_by="Sticker.position"
    )


class Sticker(Base):
    """Отдельный стикер."""
    __tablename__ = "stickers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    pack_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sticker_packs.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(256), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_animated: Mapped[bool] = mapped_column(Boolean, default=False)
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False, default="image/png")
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Relationships
    pack: Mapped["StickerPack"] = relationship("StickerPack", back_populates="stickers")


class StickerUsage(Base):
    """Использование стикера в сообщении."""
    __tablename__ = "sticker_usages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    message_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    sticker_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("stickers.id", ondelete="CASCADE"), nullable=False
    )

    # Relationships
    message: Mapped["Message"] = relationship("Message", back_populates="sticker")
    sticker: Mapped["Sticker"] = relationship("Sticker")


class ReadState(Base):
    """Состояние прочтения чата пользователем (для непрочитанных)."""
    __tablename__ = "read_states"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    chat_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    last_read_message_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    last_read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Relationships
    chat: Mapped["Chat"] = relationship("Chat", back_populates="read_states")
    user: Mapped["User"] = relationship("User", back_populates="read_states")

    __table_args__ = (
        UniqueConstraint("chat_id", "user_id", name="uq_read_state"),
    )


# ========================
# Engine & Session
# ========================

engine = create_async_engine(
    config.database_url,
    echo=False,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncSession:
    """Dependency для FastAPI — выдаёт сессию БД."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_database() -> None:
    """
    Создаёт все таблицы в БД при первом запуске.
    Также создаёт общий чат #general, если его нет.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Создаём #general, если не существует
    async with async_session_factory() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(Chat).where(Chat.chat_type == ChatType.GENERAL.value)
        )
        general_chat = result.scalar_one_or_none()

        if general_chat is None:
            general_chat = Chat(
                id=generate_uuid(),
                chat_type=ChatType.GENERAL.value,
                name="general",
            )
            session.add(general_chat)
            await session.commit()