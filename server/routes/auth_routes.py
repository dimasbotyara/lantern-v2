"""
Lantern v2 — Authentication Routes
Регистрация, логин, профиль пользователя.
"""

import aiofiles
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.database import (
    get_session, User, Chat, ChatMember, ChatType, UserStatus, generate_uuid
)
from server.models import (
    RegisterRequest, LoginRequest, AuthResponse,
    UserResponse, UserProfileUpdate
)
from server.auth import (
    hash_password, verify_password, create_access_token, get_current_user
)
from server.config import config

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
        request: RegisterRequest,
        session: AsyncSession = Depends(get_session),
) -> AuthResponse:
    """
    Регистрация нового пользователя.
    После регистрации автоматически возвращает токен (автологин).
    Также автоматически добавляет пользователя в #general.
    """
    # Проверяем уникальность username
    existing = await session.execute(
        select(User).where(User.username == request.username.lower())
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Пользователь с таким логином уже существует"
        )

    # Создаём пользователя
    user = User(
        id=generate_uuid(),
        username=request.username.lower(),
        display_name=request.display_name,
        password_hash=hash_password(request.password),
        nick_color=request.nick_color,
        status=UserStatus.ONLINE.value,
    )
    session.add(user)
    await session.flush()  # Получаем ID до коммита

    # Добавляем в #general
    general_result = await session.execute(
        select(Chat).where(Chat.chat_type == ChatType.GENERAL.value)
    )
    general_chat = general_result.scalar_one_or_none()

    if general_chat:
        membership = ChatMember(
            id=generate_uuid(),
            chat_id=general_chat.id,
            user_id=user.id,
        )
        session.add(membership)

    await session.commit()

    # Генерируем токен
    token = create_access_token(user.id, user.username)

    return AuthResponse(
        token=token,
        user=UserResponse(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            nick_color=user.nick_color,
            avatar_path=user.avatar_path,
            status=user.status,
            custom_status_text=user.custom_status_text,
            last_seen=user.last_seen,
        )
    )


@router.post("/login", response_model=AuthResponse)
async def login(
        request: LoginRequest,
        session: AsyncSession = Depends(get_session),
) -> AuthResponse:
    """
    Вход в аккаунт.
    Возвращает JWT-токен при успешной авторизации.
    """
    result = await session.execute(
        select(User).where(User.username == request.username.lower())
    )
    user = result.scalar_one_or_none()

    if user is None or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль"
        )

    # Генерируем токен
    token = create_access_token(user.id, user.username)

    return AuthResponse(
        token=token,
        user=UserResponse(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            nick_color=user.nick_color,
            avatar_path=user.avatar_path,
            status=user.status,
            custom_status_text=user.custom_status_text,
            last_seen=user.last_seen,
        )
    )


@router.get("/me", response_model=UserResponse)
async def get_me(
        current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Получить информацию о текущем пользователе."""
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        display_name=current_user.display_name,
        nick_color=current_user.nick_color,
        avatar_path=current_user.avatar_path,
        status=current_user.status,
        custom_status_text=current_user.custom_status_text,
        last_seen=current_user.last_seen,
    )


@router.put("/me", response_model=UserResponse)
async def update_profile(
        update: UserProfileUpdate,
        current_user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
) -> UserResponse:
    """Обновить профиль текущего пользователя."""
    if update.display_name is not None:
        current_user.display_name = update.display_name
    if update.nick_color is not None:
        current_user.nick_color = update.nick_color
    if update.custom_status_text is not None:
        current_user.custom_status_text = update.custom_status_text
    if update.status is not None:
        current_user.status = update.status

    session.add(current_user)
    await session.commit()
    await session.refresh(current_user)

    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        display_name=current_user.display_name,
        nick_color=current_user.nick_color,
        avatar_path=current_user.avatar_path,
        status=current_user.status,
        custom_status_text=current_user.custom_status_text,
        last_seen=current_user.last_seen,
    )


@router.post("/me/avatar", response_model=UserResponse)
async def upload_avatar(
        file: UploadFile = File(...),
        current_user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
) -> UserResponse:
    """
    Загрузить аватар пользователя.
    Принимает изображения (jpg, png, webp, gif).
    Максимальный размер — 5 MB.
    """
    # Проверяем тип файла
    allowed_types = {"image/jpeg", "image/png", "image/webp", "image/gif"}
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Неподдерживаемый формат. Допустимые: {', '.join(allowed_types)}"
        )

    # Читаем файл
    content = await file.read()

    # Проверяем размер (5 MB)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Максимальный размер аватара — 5 MB"
        )

    # Сохраняем
    avatars_dir = config.storage_path / "avatars"
    avatars_dir.mkdir(parents=True, exist_ok=True)

    # Удаляем старый аватар если есть
    if current_user.avatar_path:
        old_path = Path(current_user.avatar_path)
        if old_path.exists():
            old_path.unlink(missing_ok=True)

    # Генерируем имя файла
    ext = Path(file.filename).suffix if file.filename else ".png"
    avatar_filename = f"{current_user.id}_{uuid.uuid4().hex[:8]}{ext}"
    avatar_path = avatars_dir / avatar_filename

    async with aiofiles.open(avatar_path, "wb") as f:
        await f.write(content)

    # Обновляем путь в БД
    current_user.avatar_path = str(avatar_path)
    session.add(current_user)
    await session.commit()
    await session.refresh(current_user)

    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        display_name=current_user.display_name,
        nick_color=current_user.nick_color,
        avatar_path=current_user.avatar_path,
        status=current_user.status,
        custom_status_text=current_user.custom_status_text,
        last_seen=current_user.last_seen,
    )


@router.get("/users", response_model=list[UserResponse])
async def get_all_users(
        current_user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
) -> list[UserResponse]:
    """Получить список всех пользователей (для сайдбара контактов)."""
    result = await session.execute(
        select(User).order_by(User.display_name)
    )
    users = result.scalars().all()

    return [
        UserResponse(
            id=u.id,
            username=u.username,
            display_name=u.display_name,
            nick_color=u.nick_color,
            avatar_path=u.avatar_path,
            status=u.status,
            custom_status_text=u.custom_status_text,
            last_seen=u.last_seen,
        )
        for u in users
    ]


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
        user_id: str,
        current_user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
) -> UserResponse:
    """Получить информацию о конкретном пользователе."""
    result = await session.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден"
        )

    return UserResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        nick_color=user.nick_color,
        avatar_path=user.avatar_path,
        status=user.status,
        custom_status_text=user.custom_status_text,
        last_seen=user.last_seen,
    )


@router.post("/verify-token", response_model=UserResponse)
async def verify_token(
        current_user: User = Depends(get_current_user),
) -> UserResponse:
    """
    Проверка валидности токена.
    Используется клиентом при автологине — если токен валиден,
    возвращает информацию о пользователе.
    """
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        display_name=current_user.display_name,
        nick_color=current_user.nick_color,
        avatar_path=current_user.avatar_path,
        status=current_user.status,
        custom_status_text=current_user.custom_status_text,
        last_seen=current_user.last_seen,
    )