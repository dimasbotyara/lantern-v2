"""
Lantern v2 — Client Helper Utilities
Форматирование, конвертация, утилиты для UI.
"""

from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional


def format_file_size(size_bytes: int) -> str:
    """
    Форматирует размер файла в человекочитаемый вид.

    Examples:
        format_file_size(512) -> "512 Б"
        format_file_size(1536) -> "1.5 КБ"
        format_file_size(1048576) -> "1.0 МБ"
        format_file_size(1073741824) -> "1.0 ГБ"
    """
    if size_bytes < 0:
        return "0 Б"

    units = [
        (1024 ** 4, "ТБ"),
        (1024 ** 3, "ГБ"),
        (1024 ** 2, "МБ"),
        (1024, "КБ"),
    ]

    for threshold, unit in units:
        if size_bytes >= threshold:
            value = size_bytes / threshold
            if value >= 100:
                return f"{value:.0f} {unit}"
            elif value >= 10:
                return f"{value:.1f} {unit}"
            else:
                return f"{value:.2f} {unit}"

    return f"{size_bytes} Б"


def format_timestamp(iso_string: Optional[str], show_date: bool = False) -> str:
    """
    Форматирует ISO timestamp в отображаемое время.

    Args:
        iso_string: ISO 8601 строка.
        show_date: Показывать дату или только время.

    Returns:
        Форматированная строка.

    Examples:
        "14:32"
        "Вчера в 14:32"
        "28.05 в 14:32"
    """
    if not iso_string:
        return ""

    try:
        if isinstance(iso_string, str):
            dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        else:
            dt = iso_string

        # Конвертируем в локальное время
        local_dt = dt.astimezone(tz=None)

        if not show_date:
            return local_dt.strftime("%H:%M")

        now = datetime.now().astimezone(tz=None)
        today = now.date()
        msg_date = local_dt.date()

        if msg_date == today:
            return local_dt.strftime("%H:%M")
        elif msg_date == today - timedelta(days=1):
            return f"Вчера в {local_dt.strftime('%H:%M')}"
        elif msg_date.year == today.year:
            return local_dt.strftime("%d.%m в %H:%M")
        else:
            return local_dt.strftime("%d.%m.%Y в %H:%M")

    except (ValueError, TypeError):
        return ""


def format_date_separator(iso_string: Optional[str]) -> str:
    """
    Форматирует дату для разделителя в чате.

    Returns:
        "Сегодня", "Вчера", "28 мая", "28 мая 2023"
    """
    if not iso_string:
        return ""

    try:
        if isinstance(iso_string, str):
            dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        else:
            dt = iso_string

        local_dt = dt.astimezone(tz=None)
        now = datetime.now().astimezone(tz=None)
        today = now.date()
        msg_date = local_dt.date()

        if msg_date == today:
            return "Сегодня"
        elif msg_date == today - timedelta(days=1):
            return "Вчера"
        else:
            months = [
                "", "января", "февраля", "марта", "апреля", "мая", "июня",
                "июля", "августа", "сентября", "октября", "ноября", "декабря"
            ]
            day = msg_date.day
            month = months[msg_date.month]

            if msg_date.year == today.year:
                return f"{day} {month}"
            else:
                return f"{day} {month} {msg_date.year}"

    except (ValueError, TypeError):
        return ""


def format_last_seen(iso_string: Optional[str]) -> str:
    """
    Форматирует время последнего визита.

    Returns:
        "только что", "5 мин. назад", "2 ч. назад", "вчера", "28.05"
    """
    if not iso_string:
        return "неизвестно"

    try:
        if isinstance(iso_string, str):
            dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        else:
            dt = iso_string

        now = datetime.now(timezone.utc)
        diff = now - dt

        if diff.total_seconds() < 60:
            return "только что"
        elif diff.total_seconds() < 3600:
            minutes = int(diff.total_seconds() / 60)
            return f"{minutes} мин. назад"
        elif diff.total_seconds() < 86400:
            hours = int(diff.total_seconds() / 3600)
            return f"{hours} ч. назад"
        elif diff.days == 1:
            return "вчера"
        elif diff.days < 7:
            return f"{diff.days} дн. назад"
        else:
            local_dt = dt.astimezone(tz=None)
            return local_dt.strftime("%d.%m.%Y")

    except (ValueError, TypeError):
        return "неизвестно"


def format_duration(seconds: Optional[float]) -> str:
    """
    Форматирует длительность видео.

    Examples:
        format_duration(65) -> "1:05"
        format_duration(3661) -> "1:01:01"
    """
    if seconds is None or seconds < 0:
        return "0:00"

    total = int(seconds)
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60

    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def truncate_text(text: str, max_length: int = 50, suffix: str = "...") -> str:
    """Обрезает текст до указанной длины с добавлением суффикса."""
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def get_file_icon(mime_type: str) -> str:
    """
    Возвращает эмодзи-иконку для типа файла.

    Examples:
        get_file_icon("image/png") -> "🖼️"
        get_file_icon("video/mp4") -> "🎬"
        get_file_icon("application/pdf") -> "📄"
    """
    if not mime_type:
        return "📎"

    if mime_type.startswith("image/"):
        return "🖼️"
    elif mime_type.startswith("video/"):
        return "🎬"
    elif mime_type.startswith("audio/"):
        return "🎵"
    elif mime_type.startswith("text/"):
        return "📝"
    elif "pdf" in mime_type:
        return "📄"
    elif "zip" in mime_type or "rar" in mime_type or "tar" in mime_type or "7z" in mime_type:
        return "📦"
    elif "word" in mime_type or "document" in mime_type:
        return "📃"
    elif "sheet" in mime_type or "excel" in mime_type:
        return "📊"
    elif "presentation" in mime_type or "powerpoint" in mime_type:
        return "📽️"
    elif "json" in mime_type or "xml" in mime_type or "html" in mime_type:
        return "💻"
    elif "font" in mime_type:
        return "🔤"
    elif "executable" in mime_type or "x-msdownload" in mime_type:
        return "⚙️"
    else:
        return "📎"


def is_image_mime(mime_type: str) -> bool:
    """Проверяет, является ли MIME-тип изображением."""
    return mime_type.startswith("image/") if mime_type else False


def is_video_mime(mime_type: str) -> bool:
    """Проверяет, является ли MIME-тип видео."""
    return mime_type.startswith("video/") if mime_type else False


def status_to_display(status: str) -> tuple[str, str]:
    """
    Конвертирует статус в отображаемый текст и цвет.

    Returns:
        (display_text, dot_object_name)
    """
    statuses = {
        "online": ("В сети", "statusDotOnline"),
        "away": ("Отошёл", "statusDotAway"),
        "do_not_disturb": ("Не беспокоить", "statusDotDnd"),
        "invisible": ("Невидимка", "statusDotOffline"),
        "offline": ("Не в сети", "statusDotOffline"),
    }
    return statuses.get(status, ("Не в сети", "statusDotOffline"))