# Copilot Instructions for Lantern v2

Lantern v2 is an encrypted LAN messenger with a FastAPI backend and PyQt5 desktop client, supporting real-time WebSocket communication, file transfer, stickers, and polls.

## Quick Reference

**Run server locally:**
```bash
python server/main.py
```

**Run client locally:**
```bash
python client/main.py
```

**Note:** No tests or linters are included by default. The README explicitly states "Tests / linters: none included by default — run targeted checks if you add them."

## Project Structure

### Server (`server/`)
- **`main.py`** (258 lines) — FastAPI app entry point, lifespan management, WebSocket endpoint
- **`config.py`** — Configuration via `pydantic-settings` with `LANTERN_` env prefix, `.env` file support
- **`database.py`** (538 lines) — SQLAlchemy async ORM, models (User, Chat, Message, ChatMember, etc.), migrations
- **`models.py`** — Pydantic request/response schemas
- **`auth.py`** — JWT token generation, validation, WebSocket authentication
- **`encryption.py`** — Fernet-based file and message encryption
- **`file_manager.py`** — File uploads with chunking, thumbnail generation, cleanup task
- **`discovery.py`** — Zeroconf LAN service discovery
- **`routes/`** — REST API endpoints (auth_routes, chat_routes, file_routes)
- **`websocket/`** — WebSocket connection manager and message handler
- **`storage/`** — Directory structure for files, thumbnails, and stickers

### Client (`client/`)
- **`main.py`** (776 lines) — PyQt5 QMainWindow, qasync event loop, UI composition
- **`config.py`** — Client configuration (server connection, theme, notifications), stored in `~/.lantern_v2/`
- **`network/`**
  - `api_client.py` — Async HTTP client for REST API calls
  - `ws_client.py` — WebSocket client with message handling and state management
  - `file_transfer.py` — Chunked file upload/download and decryption
  - `encryption.py` — Client-side encryption utilities
  - `discovery.py` — Zeroconf discovery for auto-connecting to LAN servers
- **`ui/`** — PyQt5 widgets (ChatListSidebar, ChatView, MessageInput, LoginWidget, etc.)
- **`themes/`** — Catppuccin theme system with color palettes
- **`utils/`** — Helper functions

## Architecture Patterns

### Async/Await Everywhere
Both server and client use async/await throughout:
- **Server:** FastAPI with SQLAlchemy `async_session_factory` and `asyncio` tasks
- **Client:** PyQt5 with `qasync` to integrate asyncio event loop into Qt's event loop
- When writing async client code, use `await` and return coroutines; qasync handles Qt signal integration

### Configuration & Initialization
- **Server:** `ServerConfig` (pydantic) → `config.ensure_directories()` → `init_database()` → lifespan startup
- **Client:** `ClientConfig.load()` → `AuthTokenStorage` for per-server JWT tokens → UI initialization
- Both support `.env` files; server uses `LANTERN_` prefix

### WebSocket Design
- **One-way principle:** Messages are **routed only to the target chat's members**, not broadcast globally
- Connection manager stores `ConnectedUser` (user_id, username, websocket, current_chat_id)
- Handler processes incoming messages and sends replies to specific chat participants only
- See `server/websocket/manager.py` for routing logic

### Encryption Strategy
- **Server:** Fernet key stored in `encryption.key` file; applied to stored files and optionally to messages
- **Client:** Mirrors server-side encryption for local caching and transfer validation
- Both use cryptography library; `encryption_manager` (server) and client `encryption.py` provide utilities

### Database & ORM
- **SQLAlchemy 2.0 async** with `async_session_factory` for session management
- Models in `server/database.py`: User, Chat, ChatMember, ChatType enum, UserStatus enum, Message, MessageReply, etc.
- Use `select()` queries and `async with async_session_factory() as session:` pattern
- Automatic timestamp fields (`created_at`, `updated_at`)

### PyQt5 & UI Conventions
- **Signals & Slots:** Use `pyqtSignal` for component communication; avoid direct function calls between widgets
- **Async in UI:** Wrap network calls in `asyncio.create_task()` and connect results to Qt signals
- **Styling:** Generate stylesheets dynamically via `generate_stylesheet()` with theme colors
- **Layout composition:** Use `QVBoxLayout`, `QHBoxLayout`, `QSplitter` for flexible layouts
- **Icons & Resources:** Icons loaded from theme data; emojis fetched via web API or cached locally

## Key Conventions

### Naming & Structure
- **Server modules:** Use descriptive names (e.g., `connection_manager`, `file_manager`); group related logic by responsibility
- **Client widgets:** Class names end in `Widget`, `Dialog`, or `View`; inherit from appropriate Qt base class
- **File organization:** Both server and client use `__init__.py` for package exports; `__pycache__` ignored

### Error Handling
- **Server:** Return FastAPI exception responses (HTTPException, WebSocketException) with descriptive messages
- **Client:** Check `ApiResponse.success` and `ApiResponse.error`; show user-friendly error dialogs for network failures
- WebSocket failures trigger reconnection logic in `ws_client.py`

### Message Passing (WebSocket)
- Messages are JSON-encoded dictionaries with `type` field (e.g., "message_sent", "typing_indicator")
- Always include `chat_id` to route correctly; validation happens in handler
- Client sends messages via WebSocket after REST API creates them (redundant but provides real-time feedback)

### Themes & Colors
- Catppuccin palette with flavors (Mocha, Macchiato, Frappe, Latte) and accents (Mauve, Blue, etc.)
- Colors stored in `client/themes/catppuccin.py` as hex values
- `ThemeConfig` in `client/config.py` stores user's palette and accent choice; stylesheet regenerated on change

### File Organization
- **Server storage:** Files stored in `storage/files/`, thumbnails in `storage/thumbnails/`, stickers in `storage/stickers/`
- **Client downloads:** Configured path (default `~/Downloads/Lantern`); encrypted files decrypted on save
- Chunked transfer: Default chunk size 1 MB; configurable in `ServerConfig.chunk_size`

### Comments & Documentation
- Mix of English and Russian comments in existing code; maintain consistency with surrounding code
- Docstrings present for classes and main functions; keep them concise and descriptive

## Getting Started

1. **Activate virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # or .venv\Scripts\activate on Windows
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements-all.txt
   ```

3. **Configure (optional):**
   - Server: Create `.env` file with `LANTERN_HOST`, `LANTERN_PORT`, `LANTERN_JWT_SECRET_KEY`, etc.
   - Client: Settings saved to `~/.lantern_v2/` after first run; tweak via settings dialog in UI

4. **Run server and client:**
   ```bash
   python server/main.py &
   python client/main.py
   ```

5. **Login:** Use any username; first login auto-creates the user

## Common Tasks

### Adding a New REST API Endpoint
1. Create request/response schema in `server/models.py` (inherit from `BaseModel`)
2. Add route handler in appropriate file under `server/routes/` (auth, chat, or file)
3. Use `@app.post()`, `@app.get()`, etc.; handle `db_session` dependency
4. Return response objects; FastAPI auto-serializes them

### Adding a New WebSocket Message Type
1. Define JSON structure (dict with `type` and `chat_id` fields)
2. Add handler in `server/websocket/handler.py`; route by `chat_id` using `connection_manager`
3. Emit via `connection_manager.broadcast_to_chat(chat_id, message)`
4. On client, listen for message type in `ws_client.py` callback; emit Qt signal for UI update

### Working with Database Queries
- Always use `async with async_session_factory() as session:` context manager
- Use `select()` API: `session.execute(select(User).where(User.username == "alice"))`
- Relationships (e.g., `chat.members`) are lazy; explicitly `.joinedload()` if needed
- Don't forget `await session.commit()` after writes; `rollback()` on error

### Styling UI Changes
1. Edit color values in `client/themes/catppuccin.py` or accent logic in `generate_stylesheet()`
2. Changes apply instantly if theme is reloaded; client has a "Reload Theme" button in settings
3. Test with multiple color palettes to ensure contrast and readability
