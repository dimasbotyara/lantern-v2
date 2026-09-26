# 🏮 Lantern v2

[![Python CI](https://img.shields.io/github/actions/workflow/status/dimasbotyara/lantern-v2/python-app.yml?branch=main&style=for-the-badge&logo=github-actions&logoColor=white&label=Python%20CI)](https://github.com/dimasbotyara/lantern-v2/actions)
[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PyQt5](https://img.shields.io/badge/Qt-PyQt5-41CD52?style=for-the-badge&logo=qt&logoColor=white)](https://www.qt.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

Lantern v2 is an encrypted LAN messenger written in Python. It includes a FastAPI-based server and a PyQt5 desktop client. The project aims to provide private, local-network chat with file transfer, stickers, polls, and WebSocket-based real-time messaging.

## Repository layout

- `server/` — FastAPI server, WebSocket handler, routes, storage and discovery
- `client/` — PyQt5 desktop client
- `requirements-all.txt` — consolidated Python dependencies
- `requirements-client.txt`, `requirements-hosting.txt` — split dependency files
- `LICENSE` — project license

## Requirements

- Python 3.10+ (project uses modern asyncio and typing features)
- Virtual environment recommended
- Linux desktop users: PyQt5 requires Qt plugins (client includes a runtime fix for venv installs)

## Quick start

1. Create and activate a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

2. Install dependencies

```bash
pip install -r requirements-all.txt
```

3. Run the server (default: 0.0.0.0:8190)

```bash
python server/main.py
# or using uvicorn:
# uvicorn server.main:app --host 0.0.0.0 --port 8190 --reload
```

4. Run the client

```bash
python client/main.py
```

## Configuration

- Server config: `server/config.py` (uses pydantic-settings). Environment variables with `LANTERN_` prefix are supported and `.env` file is read.
  - Default host: `0.0.0.0`
  - Default port: `8190`
  - Default DB: `sqlite+aiosqlite:///./lantern_v2.db`
- Client config: `client/config.py` — settings are stored in `~/.lantern_v2` (server host/port, theme, tokens, download path).

## Features

- Encrypted messages and file storage (encryption key file: `./encryption.key` by default)
- WebSocket real-time messaging
- JWT-based authentication for API and WebSocket
- File uploads with chunked transfer and periodic storage cleanup
- Zeroconf service discovery for LAN auto-discovery
- Sticker packs & thumbnails
- Themes and system notifications for desktop client

## Development

- Use the virtualenv and install `requirements-all.txt`.
- Run server locally and connect the client to `localhost:8190`.
- Tests / linters: none included by default — run targeted checks if you add them.

## Troubleshooting

- PyQt5 on some Linux systems may require additional system packages (xcb, libxkbcommon, etc.). The client includes a Qt plugin path fix to prefer venv-provided Qt plugins.
- If the server fails to bind, check `LANTERN_HOST` / `LANTERN_PORT` environment variables or `.env` file.
- Database is SQLite by default; change `database_url` in `server/config.py` to use other DBs.

## Contributing

Contributions welcome. Open an issue or submit a PR with a clear description and test steps.

## License

See the `LICENSE` file in the repository root.

## Author

Made by dimasbotyara
