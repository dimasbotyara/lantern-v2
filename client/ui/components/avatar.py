"""
Lantern v2 — Avatar Widget
Круглый аватар с индикатором статуса.
Поддерживает: загруженное изображение, генерация из инициалов,
анимированный статус-дот.
"""

import asyncio
from typing import Optional

from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout
from PyQt5.QtGui import (
    QPainter, QPixmap, QColor, QFont, QBrush, QPen,
    QPainterPath, QImage
)
from PyQt5.QtCore import Qt, QSize, QRect, QRectF, pyqtSignal, QPropertyAnimation, QEasingCurve

from client.themes.fonts import get_font_family
from client.themes.catppuccin import get_palette, AccentColor


class AvatarWidget(QWidget):
    """
    Круглый аватар с поддержкой:
    - Загруженного изображения (QPixmap)
    - Генерации из инициалов (буква на чёрном фоне акцентным цветом)
    - Индикатора статуса (зелёный/жёлтый/красный/серый кружок)

    Sizes:
    - small: 28px (в списке участников)
    - medium: 40px (в чатах, сообщениях)
    - large: 72px (в профиле)
    """

    clicked = pyqtSignal()

    SIZES = {
        "small": 28,
        "medium": 40,
        "large": 72,
    }

    STATUS_COLORS = {
        "online": "#a6e3a1",
        "away": "#f9e2af",
        "do_not_disturb": "#f38ba8",
        "invisible": "#6c7086",
        "offline": "#6c7086",
    }

    def __init__(
            self,
            size: str = "medium",
            show_status: bool = True,
            parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)

        self._size_name = size
        self._pixel_size = self.SIZES.get(size, 40)
        self._show_status = show_status

        self._pixmap: Optional[QPixmap] = None
        self._initials: str = "?"
        self._accent_color: str = "#cba6f7"
        self._status: str = "offline"
        self._bg_color: str = "#11111b"

        # Размеры
        self.setFixedSize(self._pixel_size, self._pixel_size)
        self.setCursor(Qt.PointingHandCursor)

    def set_image(self, pixmap: QPixmap) -> None:
        """Устанавливает изображение аватара."""
        self._pixmap = pixmap
        self.update()

    def set_image_from_bytes(self, data: bytes) -> None:
        """Устанавливает изображение из байтов."""
        pixmap = QPixmap()
        pixmap.loadFromData(data)
        if not pixmap.isNull():
            self._pixmap = pixmap
            self.update()

    def set_initials(self, display_name: str, accent_color: str = "#cba6f7") -> None:
        """
        Устанавливает аватар из инициалов.

        Args:
            display_name: Отображаемое имя (берётся первая буква).
            accent_color: Цвет буквы (акцентный цвет).
        """
        self._pixmap = None
        self._initials = display_name[0].upper() if display_name else "?"
        self._accent_color = accent_color
        self.update()

    def set_status(self, status: str) -> None:
        """Устанавливает статус (online/away/dnd/invisible/offline)."""
        self._status = status
        self.update()

    def clear(self) -> None:
        """Очищает аватар."""
        self._pixmap = None
        self._initials = "?"
        self.update()

    def paintEvent(self, event) -> None:
        """Рисует аватар: круглое изображение или инициалы + статус-дот."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        size = self._pixel_size
        rect = QRectF(0, 0, size, size)

        # Круглый клип
        path = QPainterPath()
        path.addEllipse(rect)
        painter.setClipPath(path)

        if self._pixmap and not self._pixmap.isNull():
            # Рисуем изображение
            scaled = self._pixmap.scaled(
                size, size,
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation,
            )
            # Центрируем
            x = (size - scaled.width()) // 2
            y = (size - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        else:
            # Рисуем фон (чёрный)
            painter.setBrush(QColor(self._bg_color))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(rect)

            # Рисуем букву
            painter.setClipping(False)
            painter.setPen(QColor(self._accent_color))

            font_size = max(10, int(size * 0.45))
            font = QFont(get_font_family("ui"), font_size, QFont.Bold)
            painter.setFont(font)
            painter.drawText(rect.toRect(), Qt.AlignCenter, self._initials)

        painter.setClipping(False)

        # Статус-дот
        if self._show_status and self._status != "invisible":
            dot_size = max(8, int(size * 0.3))
            border_width = max(2, int(size * 0.06))

            dot_x = size - dot_size
            dot_y = size - dot_size
            dot_rect = QRectF(dot_x, dot_y, dot_size, dot_size)

            # Бордер (цвет фона родителя — mantle)
            painter.setPen(Qt.NoPen)

            # Получаем цвет фона из parent (с fallback на mantle)
            parent_bg = "#181825"  # mantle по умолчанию
            if self.parent():
                bg = self.parent().palette().color(self.parent().backgroundRole())
                # QColor.isValid() и alpha > 0 — иначе берём дефолт
                if bg.isValid() and bg.alpha() > 0:
                    parent_bg = bg.name()

            painter.setBrush(QColor(parent_bg))
            border_rect = QRectF(
                dot_x - border_width,
                dot_y - border_width,
                dot_size + border_width * 2,
                dot_size + border_width * 2,
            )
            painter.drawEllipse(border_rect)

            # Дот
            status_color = self.STATUS_COLORS.get(self._status, "#6c7086")
            painter.setBrush(QColor(status_color))
            painter.drawEllipse(dot_rect)

        painter.end()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit()

    def sizeHint(self) -> QSize:
        return QSize(self._pixel_size, self._pixel_size)

    def minimumSizeHint(self) -> QSize:
        return QSize(self._pixel_size, self._pixel_size)
