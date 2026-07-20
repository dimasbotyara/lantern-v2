"""
Lantern v2 — Client-side Zeroconf Discovery
Автоматический поиск серверов Lantern в локальной сети.
"""

import asyncio
import socket
from typing import Optional
from dataclasses import dataclass

from zeroconf import Zeroconf, ServiceBrowser, ServiceListener, ServiceInfo

ZEROCONF_TYPE = "_lantern-chat._tcp.local."


@dataclass
class DiscoveredServer:
    """Найденный сервер в сети."""
    name: str
    host: str
    port: int
    version: str = "unknown"

    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"

    @property
    def http_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def ws_url(self) -> str:
        return f"ws://{self.host}:{self.port}/ws"


class ServerDiscoveryListener(ServiceListener):
    """
    Listener для Zeroconf — получает уведомления о найденных сервисах.

    ВАЖНО: методы add_service/update_service/remove_service
    вызываются из потока Zeroconf, а НЕ из потока Qt.
    Поэтому мы НЕ вызываем коллбэки напрямую, а сохраняем
    данные и уведомляем через QTimer.singleShot(0, ...),
    который выполнит коллбэк в главном потоке Qt.
    """

    def __init__(self):
        self.servers: dict[str, DiscoveredServer] = {}
        self._callbacks: list[callable] = []
        self._pending_notify = False

    def add_callback(self, callback: callable) -> None:
        """Добавляет callback, вызываемый при обнаружении/потере сервера."""
        self._callbacks.append(callback)

    def _schedule_notify(self) -> None:
        """
        Планирует уведомление коллбэков в главном потоке Qt.
        Используем QTimer.singleShot(0, ...), чтобы выполнить
        вызов в следующей итерации event loop Qt.
        """
        if self._pending_notify:
            return  # Уже запланировано, не ставим дубликат

        self._pending_notify = True

        try:
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(0, self._do_notify)
        except ImportError:
            # Fallback если Qt недоступен (тесты и т.д.)
            self._do_notify()

    def _do_notify(self) -> None:
        """Вызывает все коллбэки с текущим списком серверов (в потоке Qt)."""
        self._pending_notify = False
        servers_snapshot = list(self.servers.values())
        for cb in self._callbacks:
            try:
                cb(servers_snapshot)
            except Exception as e:
                print(f"[Discovery] Ошибка в callback: {e}")

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        """Вызывается при обнаружении нового сервиса (из потока Zeroconf!)."""
        info = zc.get_service_info(type_, name)
        if info is None:
            return

        # Парсим адрес
        addresses = info.parsed_addresses()
        if not addresses:
            return

        host = addresses[0]
        port = info.port

        # Парсим properties
        properties = {}
        if info.properties:
            for key, value in info.properties.items():
                if isinstance(key, bytes):
                    key = key.decode("utf-8", errors="ignore")
                if isinstance(value, bytes):
                    value = value.decode("utf-8", errors="ignore")
                properties[key] = value

        server_name = properties.get("name", "Lantern Server")
        version = properties.get("version", "unknown")

        server = DiscoveredServer(
            name=server_name,
            host=host,
            port=port,
            version=version,
        )

        self.servers[name] = server
        self._schedule_notify()  # Вместо прямого _notify()

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        """Вызывается при обновлении сервиса (из потока Zeroconf!)."""
        self.add_service(zc, type_, name)

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        """Вызывается при пропадании сервиса (из потока Zeroconf!)."""
        self.servers.pop(name, None)
        self._schedule_notify()  # Вместо прямого _notify()


class ServerDiscovery:
    """
    Поиск серверов Lantern в локальной сети через Zeroconf.

    Использование:
        discovery = ServerDiscovery()
        discovery.start(on_update=callback)
        ...
        discovery.stop()
    """

    def __init__(self):
        self._zeroconf: Optional[Zeroconf] = None
        self._browser: Optional[ServiceBrowser] = None
        self._listener = ServerDiscoveryListener()
        self._running = False

    def start(self, on_update: Optional[callable] = None) -> None:
        """
        Начинает поиск серверов.

        Args:
            on_update: Callback, вызываемый при изменении списка серверов.
                       Принимает list[DiscoveredServer].
                       ВЫЗЫВАЕТСЯ В ГЛАВНОМ ПОТОКЕ QT (безопасно для UI).
        """
        if self._running:
            return

        if on_update:
            self._listener.add_callback(on_update)

        try:
            self._zeroconf = Zeroconf()
            self._browser = ServiceBrowser(
                self._zeroconf,
                ZEROCONF_TYPE,
                self._listener,
            )
            self._running = True
        except Exception as e:
            print(f"[Discovery] Ошибка запуска: {e}")

    def stop(self) -> None:
        """Останавливает поиск."""
        if not self._running:
            return

        try:
            if self._browser:
                self._browser.cancel()
                self._browser = None
            if self._zeroconf:
                self._zeroconf.close()
                self._zeroconf = None
        except Exception:
            pass

        self._running = False

    @property
    def servers(self) -> list[DiscoveredServer]:
        """Текущий список найденных серверов."""
        return list(self._listener.servers.values())

    @property
    def is_running(self) -> bool:
        return self._running


# Глобальный экземпляр
server_discovery = ServerDiscovery()
