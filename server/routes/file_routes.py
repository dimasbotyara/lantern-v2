"""
Lantern v2 — File Routes
REST-эндпоинты для загрузки, скачивания и управления файлами.
Поддержка чанковой загрузки для больших файлов (до 5 GB).
"""

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.database import (
    get_session, User, Message, MessageType, FileAttachment,
    ChatMember, generate_uuid, utcnow
)
from server.models import FileUploadInitRequest, FileUploadInitResponse
from server.auth import get_current_user
from server.file_manager import file_manager
from server.encryption import encryption_manager
from server.config import config


router = APIRouter(prefix="/api/files", tags=["files"])


# ========================
# Simple Upload (< 50 MB)
# ========================

@router.post("/upload")
async def upload_file(
    chat_id: str = Form(...),
    reply_to_id: str = Form(None),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Простая загрузка файла (для файлов < 50 MB).
    Для больших файлов используйте чанковую загрузку.
    """
    # Проверяем членство в чате
    member_result = await session.execute(
        select(ChatMember).where(
            ChatMember.chat_id == chat_id,
            ChatMember.user_id == current_user.id,
        )
    )
    if member_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Вы не участник чата")

    # Читаем содержимое
    content = await file.read()

    if len(content) > config.max_file_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Максимальный размер файла: {config.max_file_size // (1024*1024*1024)} GB"
        )

    # Определяем MIME-тип
    mime_type = file.content_type or file_manager.guess_mime_type(file.filename or "file")

    # Сохраняем файл
    stored_filename, file_path = await file_manager.save_file_simple(
        file.filename or "unnamed_file",
        content,
    )

    # Генерируем превью
    thumbnail_info = await file_manager.generate_thumbnail(file_path, mime_type)

    has_thumbnail = False
    thumbnail_path = None
    image_width = None
    image_height = None
    video_duration = None

    if thumbnail_info:
        thumbnail_path, image_width, image_height = thumbnail_info
        has_thumbnail = True

    if mime_type.startswith("video/"):
        video_duration = await file_manager.get_video_duration(file_path)

    # Создаём сообщение
    message = Message(
        id=generate_uuid(),
        chat_id=chat_id,
        author_id=current_user.id,
        message_type=MessageType.FILE.value,
        reply_to_id=reply_to_id if reply_to_id and reply_to_id != "null" else None,
    )
    session.add(message)
    await session.flush()

    # Создаём запись о файле
    attachment = FileAttachment(
        id=generate_uuid(),
        message_id=message.id,
        original_filename=file.filename or "unnamed_file",
        stored_filename=stored_filename,
        file_size=len(content),
        mime_type=mime_type,
        has_thumbnail=has_thumbnail,
        thumbnail_path=thumbnail_path,
        image_width=image_width,
        image_height=image_height,
        video_duration=video_duration,
        upload_complete=True,
        total_chunks=1,
        uploaded_chunks=1,
    )
    session.add(attachment)
    await session.commit()

    return {
        "message_id": message.id,
        "file_attachment": {
            "id": attachment.id,
            "original_filename": attachment.original_filename,
            "file_size": attachment.file_size,
            "mime_type": attachment.mime_type,
            "has_thumbnail": attachment.has_thumbnail,
            "image_width": attachment.image_width,
            "image_height": attachment.image_height,
            "video_duration": attachment.video_duration,
            "upload_complete": True,
        }
    }


# ========================
# Chunked Upload (for large files)
# ========================

@router.post("/upload/init")
async def init_chunked_upload(
    request: FileUploadInitRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> FileUploadInitResponse:
    """
    Инициализация чанковой загрузки большого файла.
    Возвращает upload_id для дальнейшей загрузки чанков.
    """
    # Проверяем членство
    member_result = await session.execute(
        select(ChatMember).where(
            ChatMember.chat_id == request.chat_id,
            ChatMember.user_id == current_user.id,
        )
    )
    if member_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Вы не участник чата")

    if request.file_size > config.max_file_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Максимальный размер: {config.max_file_size // (1024*1024*1024)} GB"
        )

    # Создаём сообщение
    message = Message(
        id=generate_uuid(),
        chat_id=request.chat_id,
        author_id=current_user.id,
        message_type=MessageType.FILE.value,
        reply_to_id=request.reply_to_id,
    )
    session.add(message)
    await session.flush()

    # Инициализируем загрузку
    await file_manager.init_upload(
        upload_id=message.id,
        original_filename=request.filename,
        total_chunks=request.total_chunks,
    )

    # Создаём attachment (incomplete)
    attachment = FileAttachment(
        id=generate_uuid(),
        message_id=message.id,
        original_filename=request.filename,
        stored_filename="",  # Заполнится после первого чанка
        file_size=request.file_size,
        mime_type=request.mime_type,
        upload_complete=False,
        total_chunks=request.total_chunks,
        uploaded_chunks=0,
    )
    session.add(attachment)
    await session.commit()

    return FileUploadInitResponse(
        upload_id=message.id,
        file_attachment_id=attachment.id,
    )


@router.post("/upload/chunk/{upload_id}")
async def upload_chunk(
    upload_id: str,
    chunk_index: int = Form(...),
    chunk: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Загрузка одного чанка файла.
    """
    data = await chunk.read()

    try:
        is_complete, stored_filename = await file_manager.save_chunk(
            upload_id=upload_id,
            chunk_index=chunk_index,
            data=data,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    # Обновляем attachment
    att_result = await session.execute(
        select(FileAttachment).where(FileAttachment.message_id == upload_id)
    )
    attachment = att_result.scalar_one_or_none()

    if attachment:
        attachment.uploaded_chunks = (attachment.uploaded_chunks or 0) + 1
        if not attachment.stored_filename:
            attachment.stored_filename = stored_filename

        if is_complete:
            attachment.upload_complete = True
            attachment.stored_filename = stored_filename

            # Генерируем превью
            file_path = file_manager.get_file_path(stored_filename)
            if file_path:
                thumb_info = await file_manager.generate_thumbnail(
                    file_path, attachment.mime_type
                )
                if thumb_info:
                    attachment.thumbnail_path = thumb_info[0]
                    attachment.image_width = thumb_info[1]
                    attachment.image_height = thumb_info[2]
                    attachment.has_thumbnail = True

                if attachment.mime_type.startswith("video/"):
                    attachment.video_duration = await file_manager.get_video_duration(file_path)

        session.add(attachment)
        await session.commit()

    return {
        "chunk_index": chunk_index,
        "is_complete": is_complete,
        "uploaded_chunks": attachment.uploaded_chunks if attachment else 0,
    }


# ========================
# Download
# ========================

@router.get("/download/{file_id}")
async def download_file(
    file_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Скачать файл по ID attachment."""
    result = await session.execute(
        select(FileAttachment).where(FileAttachment.id == file_id)
    )
    attachment = result.scalar_one_or_none()

    if attachment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Файл не найден")

    if not attachment.upload_complete:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Загрузка не завершена")

    file_path = file_manager.get_file_path(attachment.stored_filename)
    if file_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Файл не найден на диске")

    return FileResponse(
        path=str(file_path),
        filename=attachment.original_filename,
        media_type=attachment.mime_type,
    )


# ========================
# Thumbnail
# ========================

@router.get("/thumbnail/{file_id}")
async def get_thumbnail(
    file_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Получить превью файла (изображение/видео)."""
    result = await session.execute(
        select(FileAttachment).where(FileAttachment.id == file_id)
    )
    attachment = result.scalar_one_or_none()

    if attachment is None or not attachment.has_thumbnail or not attachment.thumbnail_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Превью не найдено")

    thumb_path = file_manager.get_thumbnail_path(attachment.thumbnail_path)
    if thumb_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Файл превью не найден")

    # Определяем тип превью
    suffix = thumb_path.suffix.lower()
    media_type = "image/jpeg" if suffix == ".jpg" else "image/png"

    return FileResponse(path=str(thumb_path), media_type=media_type)


# ========================
# Sticker File
# ========================

@router.get("/sticker/{sticker_id}")
async def get_sticker_file(
    sticker_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Получить файл стикера."""
    from server.database import Sticker
    result = await session.execute(
        select(Sticker).where(Sticker.id == sticker_id)
    )
    sticker = result.scalar_one_or_none()

    if sticker is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Стикер не найден")

    sticker_path = Path(sticker.filename)
    if not sticker_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Файл стикера не найден")

    return FileResponse(
        path=str(sticker_path),
        media_type=sticker.mime_type,
    )


# ========================
# Avatar
# ========================

@router.get("/avatar/{user_id}")
async def get_avatar(
    user_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Получить аватар пользователя."""
    result = await session.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if user is None or not user.avatar_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Аватар не найден")

    avatar_path = Path(user.avatar_path)
    if not avatar_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Файл аватара не найден")

    suffix = avatar_path.suffix.lower()
    media_types = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}
    media_type = media_types.get(suffix, "image/png")

    return FileResponse(path=str(avatar_path), media_type=media_type)