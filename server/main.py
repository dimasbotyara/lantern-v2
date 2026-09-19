"""
Lantern v2 — Server Entry Point
FastAPI-приложение с WebSocket, REST API, Zeroconf и автоочисткой файлов.
"""

import asyncio
import json
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from server.config import config
from server.database import init_database, async_session_factory, generate_uuid
from server.database import StickerPack, Sticker
from server.encryption import encryption_manager
from server.file_manager import file_manager
from server.discovery import service_discovery
from server.auth import authenticate_websocket
from server.websocket.manager import connection_manager
from server.websocket.handler import WebSocketHandler
from server.routes.auth_routes import router as auth_router
from server.routes.chat_routes import router as chat_router
from server.routes.file_routes import router as file_router


# ========================
# Lifespan
# ========================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle сервера:
    1. При запуске: инициализация БД, шифрования, Zeroconf, стикеров
    2. При остановке: очистка ресурсов
    """
    print("=" * 50)
    print("  🏮 Lantern v2 Server Starting...")
    print("=" * 50)

    # Создаём директории
    config.ensure_directories()

    # Инициализируем БД
    await init_database()
    print("[DB] База данных инициализирована")

    # Проверяем ключ шифрования
    print(f"[Encryption] Ключ {'загружен' if encryption_manager.key_exists else 'создан'}")

    # Сканируем стикеры
    await _load_stickers()

    # Запускаем Zeroconf
    try:
        await service_discovery.register()
    except Exception as e:
        print(f"[Zeroconf] Ошибка регистрации: {e}")
        print("[Zeroconf] Клиенты могут подключиться вручную по IP")

    # Запускаем автоочистку файлов (каждый час, удаляет файлы старше 7 дней)
    cleanup_task = asyncio.create_task(file_manager.start_cleanup_scheduler())

    print(f"[Server] Запущен на http://{config.host}:{config.port}")
    print(f"[Server] WebSocket: ws://{config.host}:{config.port}/ws")
    print("=" * 50)

    yield

    # Shutdown
    print("\n[Server] Останавливаюсь...")

    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass

    try:
        await service_discovery.unregister()
    except Exception:
        pass

    print("[Server] Остановлен")


# ========================
# App
# ========================

app = FastAPI(
    title="Lantern v2",
    description="Encrypted LAN Messenger",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS (для локальной разработки)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Роутеры
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(file_router)

# WebSocket handler
ws_handler = WebSocketHandler(manager=connection_manager)


# ========================
# Health Check
# ========================

@app.get("/api/ping")
async def ping():
    """Проверка доступности сервера."""
    return {
        "status": "ok",
        "name": config.service_name,
        "version": "2.0.0",
        "connections": connection_manager.active_connections_count,
    }


# ========================
# WebSocket Endpoint
# ========================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Главная точка входа WebSocket.

    Подключение: ws://host:port/ws?token=JWT_TOKEN

    Все сообщения — JSON:
    {
        "event": "send_message",
        "data": { ... }
    }
    """
    # Аутентификация
    async with async_session_factory() as session:
        user = await authenticate_websocket(websocket, session)

    if user is None:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    # Подключаем
    connected_user = await connection_manager.connect(websocket, user)
    print(f"[WS] {user.display_name} ({user.username}) подключился")

    try:
        while True:
            raw_message = await websocket.receive_text()
            await ws_handler.handle_event(connected_user, raw_message)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[WS] Ошибка для {user.username}: {e}")
    finally:
        await connection_manager.disconnect(user.id, websocket=websocket)
        print(f"[WS] {user.display_name} ({user.username}) отключил соединение")


# ========================
# Sticker Loading
# ========================

async def _load_stickers():
    """Сканирует папку стикеров и загружает в БД."""
    packs_data = await file_manager.scan_sticker_packs()

    if not packs_data:
        print("[Stickers] Стикеры не найдены")
        return

    async with async_session_factory() as session:
        for pack_data in packs_data:
            # Проверяем существование пака
            from sqlalchemy import select
            result = await session.execute(
                select(StickerPack).where(
                    StickerPack.directory_name == pack_data["directory_name"]
                )
            )
            existing_pack = result.scalar_one_or_none()

            if existing_pack:
                # Пак уже есть — пропускаем
                continue

            # Создаём пак
            pack = StickerPack(
                id=generate_uuid(),
                name=pack_data["name"],
                directory_name=pack_data["directory_name"],
            )
            session.add(pack)
            await session.flush()

            # Создаём стикеры
            for sticker_data in pack_data["stickers"]:
                sticker = Sticker(
                    id=generate_uuid(),
                    pack_id=pack.id,
                    filename=sticker_data["filename"],
                    position=sticker_data["position"],
                    is_animated=sticker_data["is_animated"],
                    mime_type=sticker_data["mime_type"],
                    width=sticker_data.get("width"),
                    height=sticker_data.get("height"),
                )
                session.add(sticker)

            # Устанавливаем обложку
            if pack_data["stickers"]:
                first_sticker_result = await session.execute(
                    select(Sticker)
                    .where(Sticker.pack_id == pack.id)
                    .order_by(Sticker.position)
                    .limit(1)
                )
                first_sticker = first_sticker_result.scalar_one_or_none()
                if first_sticker:
                    pack.cover_sticker_id = first_sticker.id

        await session.commit()

    total_stickers = sum(len(p["stickers"]) for p in packs_data)
    print(f"[Stickers] Загружено: {len(packs_data)} паков, {total_stickers} стикеров")


# ========================
# Run
# ========================

def run_server():
    """Запуск сервера."""
    uvicorn.run(
        "server.main:app",
        host=config.host,
        port=config.port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    run_server()
