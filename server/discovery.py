"""
Lantern v2 — Zeroconf Service Discovery
Регистрирует сервер в локальной сети для автоматического обнаружения клиентами.
"""

import socket
import asyncio
from typing import Optional

from zeroconf import Zeroconf, ServiceInfo

from server.config import config


class ServiceDiscovery:
    """
    Управление Zeroconf-сервисом.

    Регистрирует сервер как сервис в локальной сети,
    чтобы клиенты могли автоматически его найти.
    """

    def __init__(self):
        self._zeroconf: Optional[Zeroconf] = None
        self._service_info: Optional[ServiceInfo] = None

    def _get_local_ip(self) -> str:
        """Определяет локальный IP-адрес машины."""
        try:
            # Создаём UDP-сокет и "подключаемся" к внешнему адресу
            # (реального подключения не происходит)
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    async def register(self) -> None:
        """
        Регистрирует сервис в Zeroconf.
        Клиенты смогут найти сервер по типу сервиса.
        """
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._register_sync)

    def _register_sync(self) -> None:
        """Синхронная регистрация (в executor)."""
        local_ip = self._get_local_ip()

        self._service_info = ServiceInfo(
            type_=config.zeroconf_type,
            name=f"{config.service_name}.{config.zeroconf_type}",
            addresses=[socket.inet_aton(local_ip)],
            port=config.port,
            properties={
                "version": "2.0",
                "name": config.service_name,
            },
            server=f"{socket.gethostname()}.local.",
        )

        self._zeroconf = Zeroconf()
        self._zeroconf.register_service(self._service_info)

        print(f"[Zeroconf] Сервис зарегистрирован: {config.service_name}")
        print(f"[Zeroconf] IP: {local_ip}, Port: {config.port}")

    async def unregister(self) -> None:
        """Снимает регистрацию сервиса."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._unregister_sync)

    def _unregister_sync(self) -> None:
        """Синхронная разрегистрация."""
        if self._zeroconf and self._service_info:
            self._zeroconf.unregister_service(self._service_info)
            self._zeroconf.close()
            self._zeroconf = None
            self._service_info = None
            print("[Zeroconf] Сервис снят с регистрации")


# Глобальный экземпляр
service_discovery = ServiceDiscovery()