"""
Lantern v2 — File Transfer Manager
Управление загрузкой и скачиванием файлов с отслеживанием прогресса.
"""

import asyncio
from pathlib import Path
from typing import Optional, Callable
from dataclasses import dataclass, field
from enum import Enum

from client.network.api_client import api_client


class TransferState(Enum):
    """Состояние передачи файла."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class FileTransfer:
    """Информация о текущей передаче файла."""
    transfer_id: str
    file_path: str
    file_name: str
    file_size: int
    is_upload: bool  # True = upload, False = download
    chat_id: str = ""
    state: TransferState = TransferState.PENDING
    progress: float = 0.0  # 0.0 — 1.0
    error: Optional[str] = None
    result: Optional[dict] = None

    @property
    def progress_percent(self) -> int:
        return int(self.progress * 100)

    @property
    def transferred_size(self) -> int:
        return int(self.file_size * self.progress)

    @property
    def is_active(self) -> bool:
        return self.state in (TransferState.PENDING, TransferState.IN_PROGRESS)


class FileTransferManager:
    """
    Менеджер передачи файлов.

    Управляет очередью загрузок/скачиваний,
    отслеживает прогресс, уведомляет UI.
    """

    def __init__(self):
        self._transfers: dict[str, FileTransfer] = {}
        self._on_progress: Optional[Callable] = None
        self._on_complete: Optional[Callable] = None
        self._on_error: Optional[Callable] = None
        self._transfer_counter = 0

    def set_callbacks(
            self,
            on_progress: Optional[Callable] = None,
            on_complete: Optional[Callable] = None,
            on_error: Optional[Callable] = None,
    ) -> None:
        """Устанавливает callbacks для UI."""
        self._on_progress = on_progress
        self._on_complete = on_complete
        self._on_error = on_error

    def _generate_id(self) -> str:
        """Генерирует уникальный ID для передачи."""
        self._transfer_counter += 1
        return f"transfer_{self._transfer_counter}"

    # ========================
    # Upload
    # ========================

    async def upload_file(
            self,
            chat_id: str,
            file_path: str,
            reply_to_id: Optional[str] = None,
    ) -> FileTransfer:
        """
        Загружает файл на сервер.

        Args:
            chat_id: ID чата.
            file_path: Путь к файлу.
            reply_to_id: ID сообщения для ответа.

        Returns:
            FileTransfer с информацией о загрузке.
        """
        path = Path(file_path)
        if not path.exists():
            transfer = FileTransfer(
                transfer_id=self._generate_id(),
                file_path=file_path,
                file_name=path.name,
                file_size=0,
                is_upload=True,
                chat_id=chat_id,
                state=TransferState.FAILED,
                error="Файл не найден",
            )
            return transfer

        transfer = FileTransfer(
            transfer_id=self._generate_id(),
            file_path=file_path,
            file_name=path.name,
            file_size=path.stat().st_size,
            is_upload=True,
            chat_id=chat_id,
            state=TransferState.IN_PROGRESS,
        )
        self._transfers[transfer.transfer_id] = transfer

        def on_progress(progress: float):
            transfer.progress = progress
            if self._on_progress:
                self._on_progress(transfer)

        result = await api_client.upload_file(
            chat_id=chat_id,
            file_path=file_path,
            reply_to_id=reply_to_id,
            on_progress=on_progress,
        )

        if result.success:
            transfer.state = TransferState.COMPLETED
            transfer.progress = 1.0
            transfer.result = result.data
            if self._on_complete:
                self._on_complete(transfer)
        else:
            transfer.state = TransferState.FAILED
            transfer.error = result.error
            if self._on_error:
                self._on_error(transfer)

        return transfer

    # ========================
    # Download
    # ========================

    async def download_file(
            self,
            file_id: str,
            original_filename: str,
            file_size: int,
            save_directory: str,
    ) -> FileTransfer:
        """
        Скачивает файл с сервера.

        Args:
            file_id: ID файла (attachment_id).
            original_filename: Оригинальное имя файла.
            file_size: Размер файла.
            save_directory: Директория для сохранения.

        Returns:
            FileTransfer с информацией о скачивании.
        """
        save_dir = Path(save_directory)
        save_dir.mkdir(parents=True, exist_ok=True)

        save_path = save_dir / original_filename

        # Если файл уже существует — добавляем суффикс
        counter = 1
        while save_path.exists():
            stem = Path(original_filename).stem
            suffix = Path(original_filename).suffix
            save_path = save_dir / f"{stem} ({counter}){suffix}"
            counter += 1

        transfer = FileTransfer(
            transfer_id=self._generate_id(),
            file_path=str(save_path),
            file_name=original_filename,
            file_size=file_size,
            is_upload=False,
            state=TransferState.IN_PROGRESS,
        )
        self._transfers[transfer.transfer_id] = transfer

        def on_progress(progress: float):
            transfer.progress = progress
            if self._on_progress:
                self._on_progress(transfer)

        result = await api_client.download_file(
            file_id=file_id,
            save_path=str(save_path),
            on_progress=on_progress,
        )

        if result.success:
            transfer.state = TransferState.COMPLETED
            transfer.progress = 1.0
            transfer.result = result.data
            if self._on_complete:
                self._on_complete(transfer)
        else:
            transfer.state = TransferState.FAILED
            transfer.error = result.error
            if self._on_error:
                self._on_error(transfer)

        return transfer

    # ========================
    # Queries
    # ========================

    def get_active_transfers(self) -> list[FileTransfer]:
        """Возвращает список активных передач."""
        return [t for t in self._transfers.values() if t.is_active]

    def get_transfer(self, transfer_id: str) -> Optional[FileTransfer]:
        """Получает передачу по ID."""
        return self._transfers.get(transfer_id)

    def clear_completed(self) -> None:
        """Удаляет завершённые передачи из списка."""
        completed_ids = [
            tid for tid, t in self._transfers.items()
            if t.state in (TransferState.COMPLETED, TransferState.FAILED, TransferState.CANCELLED)
        ]
        for tid in completed_ids:
            del self._transfers[tid]


# Глобальный экземпляр
file_transfer_manager = FileTransferManager()