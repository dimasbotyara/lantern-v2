"""
Lantern v2 — File Manager
Управление файлами: чанковая загрузка, генерация превью,
автоудаление файлов старше 7 дней.
"""

import os
import uuid
import asyncio
import mimetypes
import subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional

import aiofiles
from PIL import Image

from server.config import config
from server.encryption import encryption_manager


class FileManager:
    """
    Менеджер файлов.

    Отвечает за:
    - Чанковую загрузку больших файлов
    - Генерацию превью для изображений и видео
    - Автоудаление файлов старше 7 дней
    - Шифрование файлов на диске
    """

    def __init__(self):
        config.ensure_directories()
        # Словарь для отслеживания чанковых загрузок
        # { upload_id: { "chunks_received": set(), "total": int, "path": Path } }
        self._active_uploads: dict[str, dict] = {}

    # ========================
    # File Upload
    # ========================

    async def init_upload(
            self,
            upload_id: str,
            original_filename: str,
            total_chunks: int,
    ) -> Path:
        """
        Инициализирует чанковую загрузку файла.

        Args:
            upload_id: Уникальный ID загрузки (обычно message_id).
            original_filename: Оригинальное имя файла.
            total_chunks: Общее количество чанков.

        Returns:
            Путь к файлу на диске.
        """
        ext = Path(original_filename).suffix
        stored_filename = f"{uuid.uuid4().hex}{ext}"
        file_path = config.storage_path / stored_filename

        self._active_uploads[upload_id] = {
            "chunks_received": set(),
            "total": total_chunks,
            "path": file_path,
            "stored_filename": stored_filename,
        }

        return file_path

    async def save_chunk(
            self,
            upload_id: str,
            chunk_index: int,
            data: bytes,
    ) -> tuple[bool, str]:
        """
        Сохраняет чанк файла.

        Args:
            upload_id: ID загрузки.
            chunk_index: Индекс чанка (0-based).
            data: Байты чанка.

        Returns:
            Tuple[is_complete, stored_filename]
        """
        upload_info = self._active_uploads.get(upload_id)
        if upload_info is None:
            raise ValueError(f"Upload {upload_id} not found")

        file_path: Path = upload_info["path"]

        # Записываем чанк (append)
        mode = "ab" if chunk_index > 0 else "wb"
        async with aiofiles.open(file_path, mode) as f:
            await f.write(data)

        upload_info["chunks_received"].add(chunk_index)

        # Проверяем завершённость
        is_complete = len(upload_info["chunks_received"]) >= upload_info["total"]

        if is_complete:
            stored_filename = upload_info["stored_filename"]
            del self._active_uploads[upload_id]
            return True, stored_filename

        return False, upload_info["stored_filename"]

    async def save_file_simple(
            self,
            original_filename: str,
            data: bytes,
    ) -> tuple[str, Path]:
        """
        Простое сохранение файла (без чанков, для маленьких файлов).

        Args:
            original_filename: Оригинальное имя файла.
            data: Содержимое файла.

        Returns:
            Tuple[stored_filename, file_path]
        """
        ext = Path(original_filename).suffix
        stored_filename = f"{uuid.uuid4().hex}{ext}"
        file_path = config.storage_path / stored_filename

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(data)

        return stored_filename, file_path

    # ========================
    # Thumbnails
    # ========================

    async def generate_thumbnail(
            self,
            file_path: Path,
            mime_type: str,
    ) -> Optional[tuple[str, int, int]]:
        """
        Генерирует превью для изображения или видео.

        Args:
            file_path: Путь к оригинальному файлу.
            mime_type: MIME-тип файла.

        Returns:
            Tuple[thumbnail_path, width, height] или None.
        """
        if mime_type.startswith("image/"):
            return await self._generate_image_thumbnail(file_path)
        elif mime_type.startswith("video/"):
            return await self._generate_video_thumbnail(file_path)
        return None

    async def _generate_image_thumbnail(
            self,
            file_path: Path,
    ) -> Optional[tuple[str, int, int]]:
        """Генерирует превью для изображения."""
        try:
            # Выполняем в executor чтобы не блокировать event loop
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, self._create_image_thumbnail_sync, file_path
            )
        except Exception as e:
            print(f"Error generating image thumbnail: {e}")
            return None

    def _create_image_thumbnail_sync(
            self,
            file_path: Path,
    ) -> Optional[tuple[str, int, int]]:
        """Синхронная генерация превью изображения (выполняется в executor)."""
        try:
            with Image.open(file_path) as img:
                original_width, original_height = img.size

                # Превью
                thumb = img.copy()
                thumb.thumbnail(config.thumbnail_max_size, Image.Resampling.LANCZOS)

                # Сохраняем как JPEG (или PNG для прозрачных)
                thumb_filename = f"thumb_{file_path.stem}.jpg"
                thumb_path = config.thumbnails_path / thumb_filename

                if img.mode in ("RGBA", "LA", "P"):
                    thumb_filename = f"thumb_{file_path.stem}.png"
                    thumb_path = config.thumbnails_path / thumb_filename
                    thumb.save(thumb_path, "PNG", optimize=True)
                else:
                    thumb = thumb.convert("RGB")
                    thumb.save(thumb_path, "JPEG", quality=85, optimize=True)

                return str(thumb_path), original_width, original_height
        except Exception:
            return None

    async def _generate_video_thumbnail(
            self,
            file_path: Path,
    ) -> Optional[tuple[str, int, int]]:
        """Генерирует превью для видео (первый кадр через ffmpeg)."""
        try:
            thumb_filename = f"thumb_{file_path.stem}.jpg"
            thumb_path = config.thumbnails_path / thumb_filename

            # Используем ffmpeg для извлечения первого кадра
            process = await asyncio.create_subprocess_exec(
                "ffmpeg", "-i", str(file_path),
                "-vframes", "1",
                "-vf", f"scale={config.thumbnail_max_size[0]}:-1",
                "-y", str(thumb_path),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await process.wait()

            if thumb_path.exists():
                # Получаем размеры оригинального видео
                width, height = await self._get_video_dimensions(file_path)
                return str(thumb_path), width or 0, height or 0

            return None
        except FileNotFoundError:
            # ffmpeg не установлен
            print("ffmpeg not found — video thumbnails disabled")
            return None
        except Exception as e:
            print(f"Error generating video thumbnail: {e}")
            return None

    async def _get_video_dimensions(
            self,
            file_path: Path,
    ) -> tuple[Optional[int], Optional[int]]:
        """Получает размеры видео через ffprobe."""
        try:
            process = await asyncio.create_subprocess_exec(
                "ffprobe",
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=p=0",
                str(file_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await process.communicate()

            if stdout:
                parts = stdout.decode().strip().split(",")
                if len(parts) == 2:
                    return int(parts[0]), int(parts[1])
            return None, None
        except Exception:
            return None, None

    async def get_video_duration(self, file_path: Path) -> Optional[float]:
        """Получает длительность видео через ffprobe."""
        try:
            process = await asyncio.create_subprocess_exec(
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "csv=p=0",
                str(file_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await process.communicate()

            if stdout:
                return float(stdout.decode().strip())
            return None
        except Exception:
            return None

    # ========================
    # File Retrieval
    # ========================

    def get_file_path(self, stored_filename: str) -> Optional[Path]:
        """
        Возвращает полный путь к файлу по имени хранения.

        Args:
            stored_filename: Имя файла на диске.

        Returns:
            Path или None если файл не существует.
        """
        file_path = config.storage_path / stored_filename
        if file_path.exists():
            return file_path
        return None

    def get_thumbnail_path(self, thumbnail_path: str) -> Optional[Path]:
        """
        Возвращает путь к превью.

        Args:
            thumbnail_path: Путь к превью из БД.

        Returns:
            Path или None.
        """
        path = Path(thumbnail_path)
        if path.exists():
            return path
        return None

    def guess_mime_type(self, filename: str) -> str:
        """Определяет MIME-тип по расширению файла."""
        mime_type, _ = mimetypes.guess_type(filename)
        return mime_type or "application/octet-stream"

    # ========================
    # Auto-Cleanup (7 days)
    # ========================

    async def cleanup_old_files(self) -> dict:
        """
        Удаляет файлы старше 7 дней.
        Возвращает статистику удаления.

        Returns:
            {"deleted_files": int, "deleted_thumbnails": int, "freed_bytes": int}
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        stats = {"deleted_files": 0, "deleted_thumbnails": 0, "freed_bytes": 0}

        # Очищаем основные файлы
        await self._cleanup_directory(config.storage_path, cutoff, stats, "deleted_files")

        # Очищаем превью
        await self._cleanup_directory(config.thumbnails_path, cutoff, stats, "deleted_thumbnails")

        return stats

    async def _cleanup_directory(
            self,
            directory: Path,
            cutoff: datetime,
            stats: dict,
            counter_key: str,
    ) -> None:
        """Удаляет файлы старше cutoff из указанной директории."""
        if not directory.exists():
            return

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, self._cleanup_directory_sync, directory, cutoff, stats, counter_key
        )

    def _cleanup_directory_sync(
            self,
            directory: Path,
            cutoff: datetime,
            stats: dict,
            counter_key: str,
    ) -> None:
        """Синхронная очистка директории (в executor)."""
        for file_path in directory.iterdir():
            if not file_path.is_file():
                continue

            # Получаем время модификации файла
            file_mtime = datetime.fromtimestamp(
                file_path.stat().st_mtime,
                tz=timezone.utc
            )

            if file_mtime < cutoff:
                file_size = file_path.stat().st_size
                try:
                    file_path.unlink()
                    stats[counter_key] += 1
                    stats["freed_bytes"] += file_size
                except OSError:
                    pass

    async def start_cleanup_scheduler(self) -> None:
        """
        Запускает периодическую очистку файлов.
        Проверяет каждый час, удаляет файлы старше 7 дней.
        """
        while True:
            try:
                stats = await self.cleanup_old_files()
                if stats["deleted_files"] > 0 or stats["deleted_thumbnails"] > 0:
                    freed_mb = stats["freed_bytes"] / (1024 * 1024)
                    print(
                        f"[Cleanup] Удалено файлов: {stats['deleted_files']}, "
                        f"превью: {stats['deleted_thumbnails']}, "
                        f"освобождено: {freed_mb:.1f} MB"
                    )
            except Exception as e:
                print(f"[Cleanup] Ошибка: {e}")

            # Ждём 1 час
            await asyncio.sleep(3600)

    # ========================
    # Stickers
    # ========================

    async def scan_sticker_packs(self) -> list[dict]:
        """
        Сканирует директорию стикеров и возвращает найденные паки.

        Ожидаемая структура:
        storage/stickers/
        ├── pack_name_1/
        │   ├── 1.png
        │   ├── 2.webp
        │   ├── 3.gif  (анимированный)
        │   └── ...
        ├── pack_name_2/
        │   └── ...

        Returns:
            Список словарей с информацией о паках.
        """
        packs = []
        stickers_dir = config.stickers_path

        if not stickers_dir.exists():
            return packs

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._scan_sticker_packs_sync
        )

    def _scan_sticker_packs_sync(self) -> list[dict]:
        """Синхронное сканирование стикеров."""
        packs = []
        stickers_dir = config.stickers_path

        for pack_dir in sorted(stickers_dir.iterdir()):
            if not pack_dir.is_dir():
                continue

            stickers = []
            supported_exts = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".apng"}

            for sticker_file in sorted(pack_dir.iterdir(), key=lambda f: self._natural_sort_key(f.stem)):
                if sticker_file.suffix.lower() not in supported_exts:
                    continue

                is_animated = sticker_file.suffix.lower() in (".gif", ".apng")
                mime_type = mimetypes.guess_type(str(sticker_file))[0] or "image/png"

                # Получаем размеры
                width, height = None, None
                try:
                    with Image.open(sticker_file) as img:
                        width, height = img.size
                except Exception:
                    pass

                stickers.append({
                    "filename": str(sticker_file),
                    "position": len(stickers),
                    "is_animated": is_animated,
                    "mime_type": mime_type,
                    "width": width,
                    "height": height,
                })

            if stickers:
                packs.append({
                    "name": pack_dir.name,
                    "directory_name": pack_dir.name,
                    "stickers": stickers,
                })

        return packs

    @staticmethod
    def _natural_sort_key(text: str):
        """Ключ для натуральной сортировки (1, 2, 10 вместо 1, 10, 2)."""
        import re
        return [
            int(c) if c.isdigit() else c.lower()
            for c in re.split(r'(\d+)', text)
        ]


# Глобальный экземпляр
file_manager = FileManager()