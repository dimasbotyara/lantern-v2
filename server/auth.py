"""
Lantern v2 — Authentication Module
JWT-токены, хэширование паролей, верификация.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional

import bcrypt as bcrypt_lib
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status, WebSocket
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.config import config
from server.database import get_session, User

# ========================
# Password Hashing
# ========================

security_scheme = HTTPBearer()


def hash_password(password: str) -> str:
    """
    Хэширует пароль bcrypt напрямую, без passlib.

    Args:
        password: Открытый пароль.

    Returns:
        Хэш пароля.
    """
    password_bytes = password.encode("utf-8")
    salt = bcrypt_lib.gensalt(rounds=12)
    hashed = bcrypt_lib.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Проверяет пароль против bcrypt-хэша.

    Args:
        plain_password: Открытый пароль.
        hashed_password: Хэш из БД.

    Returns:
        True если совпадает.
    """
    try:
        return bcrypt_lib.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


# ========================
# JWT Tokens
# ========================

def create_access_token(user_id: str, username: str) -> str:
    """
    Создаёт JWT-токен для пользователя.

    Args:
        user_id: UUID пользователя.
        username: Логин пользователя.

    Returns:
        Подписанный JWT-токен.
    """
    expire = datetime.now(timezone.utc) + timedelta(hours=config.jwt_expire_hours)
    payload = {
        "user_id": user_id,
        "username": username,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, config.jwt_secret_key, algorithm=config.jwt_algorithm)
    return token


def decode_access_token(token: str) -> Optional[dict]:
    """
    Декодирует и верифицирует JWT-токен.

    Args:
        token: JWT-токен.

    Returns:
        Payload словарь или None если токен невалидный/истёк.
    """
    try:
        payload = jwt.decode(
            token,
            config.jwt_secret_key,
            algorithms=[config.jwt_algorithm]
        )
        user_id: str = payload.get("user_id")
        username: str = payload.get("username")

        if user_id is None or username is None:
            return None

        return payload
    except JWTError:
        return None


# ========================
# Dependencies
# ========================

async def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
        session: AsyncSession = Depends(get_session),
) -> User:
    """
    FastAPI dependency — извлекает текущего пользователя из JWT-токена.
    Используется в REST-эндпоинтах.

    Args:
        credentials: Bearer-токен из заголовка Authorization.
        session: Сессия БД.

    Returns:
        Объект User из БД.

    Raises:
        HTTPException 401: Если токен невалидный или пользователь не найден.
    """
    token = credentials.credentials
    payload = decode_access_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидный или истёкший токен",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload["user_id"]

    result = await session.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не найден",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def authenticate_websocket(
        websocket: WebSocket,
        session: AsyncSession,
) -> Optional[User]:
    """
    Аутентификация WebSocket-соединения.
    Токен передаётся как query-параметр: ws://host/ws?token=xxx

    Args:
        websocket: WebSocket-соединение.
        session: Сессия БД.

    Returns:
        User или None.
    """
    token = websocket.query_params.get("token")

    if not token:
        return None

    payload = decode_access_token(token)

    if payload is None:
        return None

    user_id = payload["user_id"]

    result = await session.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    return user
