"""
Lantern v2 — Pydantic Schemas
Модели для валидации входящих/исходящих данных через API и WebSocket.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator


# ========================
# Auth
# ========================

class RegisterRequest(BaseModel):
    """Запрос на регистрацию."""
    username: str = Field(..., min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(..., min_length=4, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=128)
    nick_color: str = Field(default="#cba6f7", pattern=r"^#[0-9a-fA-F]{6}$")


class LoginRequest(BaseModel):
    """Запрос на вход."""
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=4, max_length=128)


class AuthResponse(BaseModel):
    """Ответ при успешной авторизации."""
    token: str
    user: "UserResponse"


class TokenPayload(BaseModel):
    """Содержимое JWT-токена."""
    user_id: str
    username: str
    exp: datetime


# ========================
# User
# ========================

class UserResponse(BaseModel):
    """Информация о пользователе (для клиента)."""
    id: str
    username: str
    display_name: str
    nick_color: str
    avatar_path: Optional[str] = None
    status: str = "offline"
    custom_status_text: Optional[str] = None
    last_seen: Optional[datetime] = None

    class Config:
        from_attributes = True


class UserProfileUpdate(BaseModel):
    """Обновление профиля пользователя."""
    display_name: Optional[str] = Field(None, min_length=1, max_length=128)
    nick_color: Optional[str] = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")
    custom_status_text: Optional[str] = Field(None, max_length=128)
    status: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v is not None:
            allowed = {"online", "away", "do_not_disturb", "invisible", "offline"}
            if v not in allowed:
                raise ValueError(f"Status must be one of: {allowed}")
        return v


# ========================
# Chat
# ========================

class ChatResponse(BaseModel):
    """Информация о чате."""
    id: str
    chat_type: str
    name: Optional[str] = None
    members: list[UserResponse] = []
    last_message: Optional["MessageResponse"] = None
    unread_count: int = 0
    pinned_count: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


class CreateDirectChatRequest(BaseModel):
    """Запрос на создание личного чата."""
    target_user_id: str


# ========================
# Message
# ========================

class MessageResponse(BaseModel):
    """Сообщение для клиента (расшифрованное)."""
    id: str
    chat_id: str
    author: UserResponse
    message_type: str
    content: Optional[str] = None  # Расшифрованный текст
    reply_to: Optional["MessageReplyInfo"] = None
    forwarded_from: Optional[UserResponse] = None
    is_edited: bool = False
    is_deleted: bool = False
    reactions: list["ReactionInfo"] = []
    file_attachment: Optional["FileAttachmentResponse"] = None
    poll: Optional["PollResponse"] = None
    sticker: Optional["StickerResponse"] = None
    pinned: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class MessageReplyInfo(BaseModel):
    """Краткая информация об оригинальном сообщении (для reply)."""
    id: str
    author: UserResponse
    content: Optional[str] = None  # Краткий текст (обрезанный)
    is_deleted: bool = False
    message_type: str = "text"


class SendMessageRequest(BaseModel):
    """Запрос на отправку сообщения (через WebSocket)."""
    chat_id: str
    content: Optional[str] = Field(None, max_length=4096)
    message_type: str = "text"
    reply_to_id: Optional[str] = None
    forwarded_from_id: Optional[str] = None
    forwarded_message_ids: Optional[list[str]] = None  # Для множественной пересылки


class EditMessageRequest(BaseModel):
    """Запрос на редактирование сообщения."""
    message_id: str
    new_content: str = Field(..., min_length=1, max_length=4096)


class DeleteMessageRequest(BaseModel):
    """Запрос на удаление сообщения."""
    message_id: str
    for_everyone: bool = False  # True = для всех, False = только для себя


class MessageSearchRequest(BaseModel):
    """Запрос на поиск сообщений."""
    chat_id: str
    query: str = Field(..., min_length=1, max_length=256)
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=20, ge=1, le=100)


# ========================
# File Attachment
# ========================

class FileAttachmentResponse(BaseModel):
    """Информация о файле для клиента."""
    id: str
    original_filename: str
    file_size: int
    mime_type: str
    has_thumbnail: bool = False
    image_width: Optional[int] = None
    image_height: Optional[int] = None
    video_duration: Optional[float] = None
    upload_complete: bool = True

    class Config:
        from_attributes = True


class FileUploadInitRequest(BaseModel):
    """Инициализация чанковой загрузки файла."""
    chat_id: str
    filename: str
    file_size: int
    mime_type: str = "application/octet-stream"
    total_chunks: int = 1
    reply_to_id: Optional[str] = None


class FileUploadInitResponse(BaseModel):
    """Ответ на инициализацию загрузки."""
    upload_id: str  # message_id
    file_attachment_id: str


# ========================
# Reactions
# ========================

class ReactionInfo(BaseModel):
    """Агрегированная информация о реакции."""
    emoji: str
    count: int
    users: list[str] = []  # user_ids
    has_my_reaction: bool = False


class ToggleReactionRequest(BaseModel):
    """Добавить/убрать реакцию."""
    message_id: str
    emoji: str = Field(..., max_length=32)


# ========================
# Polls
# ========================

class CreatePollRequest(BaseModel):
    """Создание опроса."""
    chat_id: str
    question: str = Field(..., min_length=1, max_length=256)
    options: list[str] = Field(..., min_length=2, max_length=10)
    is_anonymous: bool = False
    is_multiple_choice: bool = False

    @field_validator("options")
    @classmethod
    def validate_options(cls, v):
        for opt in v:
            if len(opt) < 1 or len(opt) > 128:
                raise ValueError("Each option must be 1-128 characters")
        return v


class PollResponse(BaseModel):
    """Информация об опросе для клиента."""
    id: str
    question: str
    options: list["PollOptionResponse"] = []
    is_anonymous: bool = False
    is_multiple_choice: bool = False
    is_closed: bool = False
    total_votes: int = 0
    my_votes: list[str] = []  # option_ids

    class Config:
        from_attributes = True


class PollOptionResponse(BaseModel):
    """Вариант ответа в опросе."""
    id: str
    text: str
    vote_count: int = 0
    percentage: float = 0.0
    voters: list[UserResponse] = []  # Если не анонимный


class VotePollRequest(BaseModel):
    """Голосование в опросе."""
    poll_id: str
    option_ids: list[str] = Field(..., min_length=1)


# ========================
# Pin
# ========================

class PinMessageRequest(BaseModel):
    """Закрепить сообщение."""
    message_id: str
    chat_id: str


class PinnedMessageResponse(BaseModel):
    """Закреплённое сообщение для клиента."""
    id: str
    message: MessageResponse
    pinned_by: UserResponse
    pinned_at: datetime


# ========================
# Stickers
# ========================

class StickerResponse(BaseModel):
    """Информация о стикере."""
    id: str
    pack_id: str
    pack_name: str = ""
    filename: str
    is_animated: bool = False
    mime_type: str = "image/png"
    width: Optional[int] = None
    height: Optional[int] = None

    class Config:
        from_attributes = True


class StickerPackResponse(BaseModel):
    """Набор стикеров."""
    id: str
    name: str
    stickers: list[StickerResponse] = []
    cover_sticker: Optional[StickerResponse] = None


class SendStickerRequest(BaseModel):
    """Отправка стикера."""
    chat_id: str
    sticker_id: str
    reply_to_id: Optional[str] = None


# ========================
# WebSocket Events
# ========================

class WSEvent(BaseModel):
    """Базовое WebSocket-событие."""
    event: str
    data: dict = {}


class WSMessageEvent(BaseModel):
    """WS: новое сообщение."""
    event: str = "new_message"
    data: MessageResponse


class WSTypingEvent(BaseModel):
    """WS: пользователь печатает."""
    event: str = "typing"
    data: dict  # {"chat_id": ..., "user_id": ..., "username": ..., "is_typing": bool}


class WSStatusEvent(BaseModel):
    """WS: изменение статуса пользователя."""
    event: str = "status_change"
    data: dict  # {"user_id": ..., "status": ..., "last_seen": ...}


class WSReactionEvent(BaseModel):
    """WS: реакция добавлена/убрана."""
    event: str = "reaction_update"
    data: dict  # {"message_id": ..., "reactions": [...]}


class WSMessageEditEvent(BaseModel):
    """WS: сообщение отредактировано."""
    event: str = "message_edited"
    data: dict  # {"message_id": ..., "chat_id": ..., "new_content": ..., "is_edited": True}


class WSMessageDeleteEvent(BaseModel):
    """WS: сообщение удалено."""
    event: str = "message_deleted"
    data: dict  # {"message_id": ..., "chat_id": ..., "for_everyone": bool}


class WSPinEvent(BaseModel):
    """WS: сообщение закреплено/откреплено."""
    event: str = "pin_update"
    data: dict  # {"chat_id": ..., "pinned_message": ... or null, "action": "pin"/"unpin"}


class WSPollVoteEvent(BaseModel):
    """WS: голос в опросе."""
    event: str = "poll_update"
    data: dict  # {"poll_id": ..., "message_id": ..., "chat_id": ..., "poll": PollResponse}


class WSUserUpdateEvent(BaseModel):
    """WS: обновление профиля пользователя."""
    event: str = "user_update"
    data: UserResponse


# Обновляем forward references
MessageResponse.model_rebuild()
ChatResponse.model_rebuild()
PollResponse.model_rebuild()
AuthResponse.model_rebuild()
PinnedMessageResponse.model_rebuild()