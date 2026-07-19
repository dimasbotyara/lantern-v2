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
    """Listener для Zeroconf — получает уведомления о найденных сервисах."""

    def __init__(self):
        self.servers: dict[str, DiscoveredServer] = {}
        self._callbacks: list[callable] = []

    def add_callback(self, callback: callable) -> None:
        """Добавляет callback, вызываемый при обнаружении/потере сервера."""
        self._callbacks.append(callback)

    def _notify(self) -> None:
        """Уведомляет все callbacks об изменении списка серверов."""
        for cb in self._callbacks:
            try:
                cb(list(self.servers.values()))
            except Exception:
                pass

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        """Вызывается при обнаружении нового сервиса."""
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
        self._notify()

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        """Вызывается при обновлении сервиса."""
        self.add_service(zc, type_, name)

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        """Вызывается при пропадании сервиса."""
        self.servers.pop(name, None)
        self._notify()


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