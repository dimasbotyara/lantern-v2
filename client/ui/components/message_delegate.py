"""
Lantern v2 — Message Delegate (Pixel-Perfect Bubbles!)
QStyledItemDelegate для рисования сообщений через QPainter.

Каждый пузырёк рисуется вручную — это гарантирует:
1. Точный sizeHint() даже для многострочных сообщений
2. Никаких проблем с прокруткой
3. Высокую производительность (нет виджетов в списке)

Layout пузырька:
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│          [Avatar]  ┌──────────────────────────────┐         │
│                    │ ↗ Переслано от Bob           │         │
│                    │ ┃ Reply Author               │         │
│                    │ ┃ Reply text preview...       │         │
│                    │ Author Name              ⏰  │         │
│                    │ Message content text that     │         │
│                    │ can span multiple lines       │         │
│                    │                               │         │
│                    │ [🖼️ Image Preview]            │         │
│                    │ [📎 file.zip  2.4 MB]         │         │
│                    │                               │         │
│                    │ 😂3  ❤️1           14:32 ✏️  │         │
│                    └──────────────────────────────┘         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
"""

import re
from typing import Optional

from PyQt5.QtWidgets import (
    QStyledItemDelegate, QStyleOptionViewItem, QWidget, QApplication, QStyle
)
from PyQt5.QtGui import (
    QPainter, QColor, QFont, QFontMetrics, QFontMetricsF,
    QPen, QBrush, QPainterPath, QTextDocument, QTextOption,
    QAbstractTextDocumentLayout, QPixmap, QLinearGradient
)
from PyQt5.QtCore import (
    Qt, QSize, QRect, QRectF, QPoint, QPointF, QModelIndex, QSizeF
)

from client.ui.components.message_model import MessageRole
from client.utils.helpers import format_timestamp, format_file_size, get_file_icon
from client.themes.fonts import get_font_family, get_font_css_stack
from client.themes.catppuccin import get_palette, Palette, AccentColor


class MessageDelegate(QStyledItemDelegate):
    """
    Делегат для рисования сообщений.

    Ключевые принципы:
    - Всё рисуется через QPainter — никаких виджетов
    - sizeHint() точно вычисляет высоту через QTextDocument
    - Пузырьки: свои справа (акцентный фон), чужие слева (surface0 фон)
    - Поддержка: текст, reply, forward, reactions, files, polls, stickers, markdown
    """

    # Layout constants
    HORIZONTAL_MARGIN = 16  # Отступ от края окна
    BUBBLE_MAX_WIDTH_RATIO = 0.7  # Максимальная ширина пузырька (% от ширины)
    BUBBLE_RADIUS = 16  # Скругление углов
    BUBBLE_PADDING_H = 14  # Горизонтальный padding внутри пузырька
    BUBBLE_PADDING_V = 8  # Вертикальный padding
    AVATAR_SIZE = 36  # Размер аватара
    AVATAR_MARGIN = 10  # Отступ аватара от пузырька
    AUTHOR_FONT_SIZE = 13  # Размер шрифта автора
    TEXT_FONT_SIZE = 14  # Размер шрифта текста
    TIMESTAMP_FONT_SIZE = 11  # Размер шрифта времени
    REPLY_FONT_SIZE = 12  # Размер шрифта цитаты
    REACTION_FONT_SIZE = 13  # Размер шрифта реакций
    REACTION_HEIGHT = 26  # Высота полоски реакций
    REPLY_BAR_WIDTH = 3  # Ширина вертикальной полоски reply
    REPLY_PADDING = 6  # Padding внутри reply блока
    SPACING = 4  # Общий spacing между элементами
    SEPARATOR_HEIGHT = 40  # Высота разделителя даты
    UNREAD_SEPARATOR_HEIGHT = 32  # Высота разделителя непрочитанных
    GROUP_SPACING = 2  # Расстояние между сгруппированными сообщениями
    NON_GROUP_SPACING = 10  # Расстояние между несгруппированными
    FILE_PREVIEW_HEIGHT = 52  # Высота превью файла
    IMAGE_MAX_WIDTH = 320  # Макс ширина превью изображения
    IMAGE_MAX_HEIGHT = 240  # Макс высота превью изображения
    STICKER_SIZE = 160  # Размер стикера
    FORWARDED_FONT_SIZE = 12  # Размер шрифта "переслано"

    def __init__(
            self,
            palette: Palette,
            accent: AccentColor,
            current_user_id: str = "",
            parent=None,
    ):
        super().__init__(parent)
        self._palette = palette
        self._accent = accent
        self._current_user_id = current_user_id

        # Шрифты (кэшируем)
        self._font_author = QFont(get_font_family("ui"), self.AUTHOR_FONT_SIZE, QFont.DemiBold)
        self._font_text = QFont(get_font_family("ui"), self.TEXT_FONT_SIZE)
        self._font_timestamp = QFont(get_font_family("ui"), self.TIMESTAMP_FONT_SIZE)
        self._font_reply_author = QFont(get_font_family("ui"), self.REPLY_FONT_SIZE, QFont.DemiBold)
        self._font_reply_text = QFont(get_font_family("ui"), self.REPLY_FONT_SIZE)
        self._font_reaction = QFont(get_font_family("emoji"), self.REACTION_FONT_SIZE)
        self._font_separator = QFont(get_font_family("ui"), 12, QFont.DemiBold)
        self._font_edited = QFont(get_font_family("ui"), self.TIMESTAMP_FONT_SIZE, italic=True)
        self._font_forwarded = QFont(get_font_family("ui"), self.FORWARDED_FONT_SIZE, italic=True)
        self._font_file_name = QFont(get_font_family("ui"), 13, QFont.DemiBold)
        self._font_file_size = QFont(get_font_family("ui"), 11)
        self._font_code = QFont(get_font_family("code"), 13)
        if not QFontMetrics(self._font_code).height():
            self._font_code = QFont(get_font_family("code"), 13)
            if not QFontMetrics(self._font_code).height():
                self._font_code = QFont("monospace", 13)

        # Цвета (кэшируем)
        ar, ag, ab = self._accent.rgb
        self._color_own_bg = QColor(ar, ag, ab, 35)
        self._color_own_bg_hover = QColor(ar, ag, ab, 50)
        self._color_other_bg = QColor(self._palette.surface0)
        self._color_other_bg_hover = QColor(self._palette.surface1)
        self._color_text = QColor(self._palette.text)
        self._color_subtext = QColor(self._palette.subtext0)
        self._color_timestamp = QColor(self._palette.overlay0)
        self._color_accent = QColor(self._accent.hex)
        self._color_reply_bg = QColor(0, 0, 0, 20)
        self._color_separator_bg = QColor(self._palette.surface0)
        self._color_separator_text = QColor(self._palette.subtext0)
        self._color_unread_bg = QColor(self._palette.red)
        self._color_unread_text = QColor(self._palette.crust)
        self._color_edited = QColor(self._palette.overlay0)
        self._color_forwarded = QColor(self._palette.subtext0)
        self._color_code_bg = QColor(self._palette.mantle)
        self._color_link = QColor(self._accent.hex)
        self._color_reaction_bg = QColor(self._palette.surface0)
        self._color_reaction_border = QColor(self._palette.surface1)
        self._color_reaction_active_bg = QColor(ar, ag, ab, 40)
        self._color_reaction_active_border = QColor(self._accent.hex)
        self._color_deleted_text = QColor(self._palette.overlay0)
        self._color_base = QColor(self._palette.base)
        self._color_file_bg = QColor(self._palette.surface0)

        # Кэш QTextDocument для вычисления размеров
        self._size_cache: dict[str, QSize] = {}

        # Кэш QTextDocument для отрисовки (чтобы не тормозило при скролле)
        self._doc_cache: dict[str, QTextDocument] = {}

    def set_theme(self, palette: Palette, accent: AccentColor) -> None:
        """Обновляет тему без пересоздания делегата."""
        self._palette = palette
        self._accent = accent
        self._size_cache.clear()
        self._doc_cache.clear()
        # Пересоздаём цвета
        ar, ag, ab = accent.rgb
        self._color_own_bg = QColor(ar, ag, ab, 35)
        self._color_own_bg_hover = QColor(ar, ag, ab, 50)
        self._color_other_bg = QColor(palette.surface0)
        self._color_other_bg_hover = QColor(palette.surface1)
        self._color_text = QColor(palette.text)
        self._color_subtext = QColor(palette.subtext0)
        self._color_timestamp = QColor(palette.overlay0)
        self._color_accent = QColor(accent.hex)
        self._color_reply_bg = QColor(0, 0, 0, 20)
        self._color_separator_bg = QColor(palette.surface0)
        self._color_separator_text = QColor(palette.subtext0)
        self._color_unread_bg = QColor(palette.red)
        self._color_unread_text = QColor(palette.crust)
        self._color_edited = QColor(palette.overlay0)
        self._color_forwarded = QColor(palette.subtext0)
        self._color_code_bg = QColor(palette.mantle)
        self._color_link = QColor(accent.hex)
        self._color_reaction_bg = QColor(palette.surface0)
        self._color_reaction_border = QColor(palette.surface1)
        self._color_reaction_active_bg = QColor(ar, ag, ab, 40)
        self._color_reaction_active_border = QColor(accent.hex)
        self._color_deleted_text = QColor(palette.overlay0)
        self._color_base = QColor(palette.base)
        self._color_file_bg = QColor(palette.surface0)

    def set_current_user(self, user_id: str) -> None:
        self._current_user_id = user_id
        self._size_cache.clear()

    def invalidate_cache(self) -> None:
        """Сбрасывает кэш размеров (при изменении ширины окна)."""
        self._size_cache.clear()
        self._doc_cache.clear()

    def invalidate_message_cache(self, message_id: str) -> None:
        """Сбрасывает кэш для конкретного сообщения (при редактировании и т.д.)."""
        if not message_id:
            return
        prefix = f"{message_id}_"
        self._size_cache = {k: v for k, v in self._size_cache.items() if not k.startswith(prefix)}
        self._doc_cache = {k: v for k, v in self._doc_cache.items() if not k.startswith(prefix)}

    # ========================
    # sizeHint — КРИТИЧЕСКИ ВАЖНО!
    # ========================

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        """
        Вычисляет точную высоту элемента.
        Это самый важный метод — от его точности зависит прокрутка.
        """
        item_type = index.data(MessageRole.ItemType)

        if item_type == "date_separator":
            return QSize(option.rect.width(), self.SEPARATOR_HEIGHT)

        if item_type == "unread_separator":
            return QSize(option.rect.width(), self.UNREAD_SEPARATOR_HEIGHT)

        # Сообщение
        view_width = option.rect.width() if option.rect.width() > 0 else 800
        msg_id = index.data(MessageRole.MessageId)
        cache_key = f"{msg_id}_{view_width}"

        if cache_key in self._size_cache:
            return self._size_cache[cache_key]

        height = self._calculate_message_height(index, view_width)

        # Spacing
        show_author = index.data(MessageRole.ShowAuthor)
        if show_author:
            height += self.NON_GROUP_SPACING
        else:
            height += self.GROUP_SPACING

        size = QSize(view_width, height)
        self._size_cache[cache_key] = size
        return size

    def _calculate_message_height(self, index: QModelIndex, view_width: int) -> int:
        """Вычисляет высоту пузырька сообщения."""
        is_own = index.data(MessageRole.IsOwn)
        show_author = index.data(MessageRole.ShowAuthor)
        content = index.data(MessageRole.Content) or ""
        msg_type = index.data(MessageRole.MessageType)
        reply_to = index.data(MessageRole.ReplyTo)
        forwarded = index.data(MessageRole.ForwardedFrom)
        reactions = index.data(MessageRole.Reactions) or []
        file_att = index.data(MessageRole.FileAttachment)
        poll = index.data(MessageRole.Poll)
        sticker = index.data(MessageRole.Sticker)
        is_deleted = index.data(MessageRole.IsDeleted)
        is_edited = index.data(MessageRole.IsEdited)

        # Ширина пузырька
        max_bubble_w = int(view_width * self.BUBBLE_MAX_WIDTH_RATIO)
        content_width = max_bubble_w - self.BUBBLE_PADDING_H * 2

        height = self.BUBBLE_PADDING_V  # Верхний padding

        # Стикер — особый размер
        if msg_type == "sticker" and sticker:
            return self.STICKER_SIZE + self.NON_GROUP_SPACING + 24  # + timestamp

        # Forwarded
        if forwarded:
            height += QFontMetrics(self._font_forwarded).height() + self.SPACING

        # Reply
        if reply_to:
            height += self._calculate_reply_height(reply_to, content_width)
            height += self.SPACING

        # Author name
        if show_author and not is_own:
            height += QFontMetrics(self._font_author).height() + self.SPACING

        # Deleted message
        if is_deleted:
            height += QFontMetrics(self._font_text).height()
            height += self.BUBBLE_PADDING_V
            height += 20  # timestamp line
            return height

        # Content text
        if content and msg_type == "text":
            text_height = self._calculate_text_height(content, content_width)
            height += text_height + self.SPACING

        # File attachment
        if file_att:
            if file_att.get("has_thumbnail") and file_att.get("mime_type", "").startswith("image/"):
                img_w = file_att.get("image_width", 320) or 320
                img_h = file_att.get("image_height", 240) or 240
                scale = min(self.IMAGE_MAX_WIDTH / img_w, self.IMAGE_MAX_HEIGHT / img_h, 1.0)
                height += int(img_h * scale) + self.SPACING
            else:
                height += self.FILE_PREVIEW_HEIGHT + self.SPACING

        # Poll
        if poll and msg_type == "poll":
            height += self._calculate_poll_height(poll, content_width)

        # Reactions
        if reactions:
            height += self._calculate_reactions_height(reactions, content_width) + self.SPACING

        # Timestamp line (время + edited)
        height += QFontMetrics(self._font_timestamp).height() + self.SPACING

        height += self.BUBBLE_PADDING_V  # Нижний padding

        return max(height, 40)  # Минимальная высота

    def _calculate_text_height(self, text: str, max_width: int) -> int:
        """
        Вычисляет высоту текста с учётом блоков кода.
        Блоки кода измеряются отдельно — они имеют фиксированную высоту
        по количеству строк, а не через QTextDocument.
        """
        if not text:
            return 0

        total_height = 0
        segments = self._parse_segments(text)

        for seg in segments:
            if seg["type"] == "code_block":
                total_height += self._measure_code_block(seg["content"], max_width)
            elif seg["type"] == "text":
                if seg["content"].strip():
                    total_height += self._measure_text_segment(seg["content"], max_width)
            elif seg["type"] == "inline_code":
                # Инлайн-код — часть текста, рисуем как обычный текст
                # (Fira Code без фона — пока отложим, чтобы не ломать HTML)
                current_y = self._paint_text_segment(
                    painter, x, current_y, max_width,
                    seg["content"],
                    msg_id,
                )

        return total_height

    def _calculate_reply_height(self, reply: dict, max_width: int) -> int:
        """Вычисляет высоту блока reply."""
        height = self.REPLY_PADDING * 2  # Верхний + нижний padding
        height += QFontMetrics(self._font_reply_author).height()  # Имя автора
        height += 2  # Spacing
        height += QFontMetrics(self._font_reply_text).height()  # Текст
        return height

    def _calculate_reactions_height(self, reactions: list[dict], max_width: int) -> int:
        """Вычисляет высоту полоски реакций с учётом переноса строк."""
        if not reactions:
            return 0

        rx = 0
        rows = 1
        fm = QFontMetrics(self._font_reaction)

        for reaction in reactions:
            emoji = reaction.get("emoji", "")
            count = reaction.get("count", 0)
            text = f"{emoji} {count}" if count > 1 else emoji
            badge_width = fm.horizontalAdvance(text) + 16

            if rx > 0 and rx + badge_width > max_width:
                rows += 1
                rx = badge_width + 4
            else:
                rx += badge_width + 4

        return rows * self.REACTION_HEIGHT + max(0, rows - 1) * 4

    def _calculate_poll_height(self, poll: dict, max_width: int) -> int:
        """Вычисляет высоту опроса."""
        height = 0
        # Вопрос
        doc = QTextDocument()
        doc.setDefaultFont(QFont(get_font_family("ui"), 15, QFont.DemiBold))
        doc.setTextWidth(max_width)
        doc.setPlainText(poll.get("question", ""))
        height += int(doc.size().height()) + 8

        # Варианты
        options = poll.get("options", [])
        height += len(options) * 44  # Каждый вариант ~44px

        # Итого голосов
        height += 24

        return height

    # ========================
    # paint — Рисование
    # ========================

    def paint(
            self,
            painter: QPainter,
            option: QStyleOptionViewItem,
            index: QModelIndex,
    ) -> None:
        """Главный метод рисования."""
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        item_type = index.data(MessageRole.ItemType)

        if item_type == "date_separator":
            self._paint_date_separator(painter, option, index)
        elif item_type == "unread_separator":
            self._paint_unread_separator(painter, option, index)
        else:
            self._paint_message(painter, option, index)

        painter.restore()

    def _paint_date_separator(
            self,
            painter: QPainter,
            option: QStyleOptionViewItem,
            index: QModelIndex,
    ) -> None:
        """Рисует разделитель даты: ─── Сегодня ───"""
        rect = option.rect
        text = index.data(MessageRole.SeparatorText) or ""

        painter.setFont(self._font_separator)
        fm = QFontMetrics(self._font_separator)
        text_width = fm.horizontalAdvance(text) + 28  # Padding
        text_height = fm.height() + 8

        center_x = rect.center().x()
        center_y = rect.center().y()

        # Линии
        line_y = center_y
        painter.setPen(QPen(self._color_separator_bg, 1))
        painter.drawLine(rect.left() + 40, line_y, center_x - text_width // 2 - 8, line_y)
        painter.drawLine(center_x + text_width // 2 + 8, line_y, rect.right() - 40, line_y)

        # Фон текста (пилюля)
        text_rect = QRectF(
            center_x - text_width // 2,
            center_y - text_height // 2,
            text_width,
            text_height,
        )
        path = QPainterPath()
        path.addRoundedRect(text_rect, text_height // 2, text_height // 2)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._color_separator_bg)
        painter.drawPath(path)

        # Текст
        painter.setPen(self._color_separator_text)
        painter.drawText(text_rect.toRect(), Qt.AlignCenter, text)

    def _paint_unread_separator(
            self,
            painter: QPainter,
            option: QStyleOptionViewItem,
            index: QModelIndex,
    ) -> None:
        """Рисует разделитель непрочитанных: ─── Новые сообщения ───"""
        rect = option.rect
        text = "Непрочитанные сообщения"

        painter.setFont(self._font_separator)
        fm = QFontMetrics(self._font_separator)
        text_width = fm.horizontalAdvance(text) + 24
        text_height = fm.height() + 6

        center_x = rect.center().x()
        center_y = rect.center().y()

        # Красные линии
        painter.setPen(QPen(self._color_unread_bg, 1))
        painter.drawLine(rect.left() + 40, center_y, center_x - text_width // 2 - 8, center_y)
        painter.drawLine(center_x + text_width // 2 + 8, center_y, rect.right() - 40, center_y)

        # Фон (красная пилюля)
        text_rect = QRectF(
            center_x - text_width // 2,
            center_y - text_height // 2,
            text_width,
            text_height,
        )
        path = QPainterPath()
        path.addRoundedRect(text_rect, text_height // 2, text_height // 2)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._color_unread_bg)
        painter.drawPath(path)

        # Белый текст
        painter.setPen(self._color_unread_text)
        painter.drawText(text_rect.toRect(), Qt.AlignCenter, text)

    def _paint_message(
            self,
            painter: QPainter,
            option: QStyleOptionViewItem,
            index: QModelIndex,
    ) -> None:
        """Рисует пузырёк сообщения."""
        rect = option.rect
        is_own = index.data(MessageRole.IsOwn)
        show_author = index.data(MessageRole.ShowAuthor)
        show_avatar = index.data(MessageRole.ShowAvatar)
        content = index.data(MessageRole.Content) or ""
        msg_type = index.data(MessageRole.MessageType)
        author = index.data(MessageRole.AuthorData) or {}
        timestamp = index.data(MessageRole.Timestamp) or ""
        is_edited = index.data(MessageRole.IsEdited)
        is_deleted = index.data(MessageRole.IsDeleted)
        reply_to = index.data(MessageRole.ReplyTo)
        forwarded = index.data(MessageRole.ForwardedFrom)
        reactions = index.data(MessageRole.Reactions) or []
        file_att = index.data(MessageRole.FileAttachment)
        poll = index.data(MessageRole.Poll)
        sticker = index.data(MessageRole.Sticker)
        is_pinned = index.data(MessageRole.IsPinned)

        # Spacing сверху
        top_offset = self.NON_GROUP_SPACING if show_author else self.GROUP_SPACING

        # Вычисляем размеры пузырька
        view_width = rect.width()
        max_bubble_w = int(view_width * self.BUBBLE_MAX_WIDTH_RATIO)
        content_width = max_bubble_w - self.BUBBLE_PADDING_H * 2

        # Для стикера — без пузырька
        if msg_type == "sticker" and sticker:
            self._paint_sticker_message(painter, rect, is_own, sticker, timestamp, top_offset)
            return

        # Вычисляем нужную ширину пузырька (подгоняем под контент)
        needed_width = self._calculate_needed_width(
            content, msg_type, author, show_author, is_own,
            reply_to, forwarded, reactions, file_att, poll,
            is_edited, is_deleted, timestamp, content_width,
        )
        bubble_width = min(needed_width + self.BUBBLE_PADDING_H * 2, max_bubble_w)
        bubble_width = max(bubble_width, 120)  # Минимальная ширина

        actual_content_width = bubble_width - self.BUBBLE_PADDING_H * 2

        # Высота пузырька (без spacing)
        bubble_height = self._calculate_message_height(index, view_width) - top_offset

        # Позиция пузырька
        if is_own:
            bubble_x = rect.right() - bubble_width - self.HORIZONTAL_MARGIN
        else:
            avatar_offset = 0
            if show_avatar:
                avatar_offset = self.AVATAR_SIZE + self.AVATAR_MARGIN
            bubble_x = rect.left() + self.HORIZONTAL_MARGIN + avatar_offset

        bubble_y = rect.top() + top_offset

        # === Рисуем аватар ===
        if show_avatar and not is_own:
            self._paint_avatar(
                painter,
                rect.left() + self.HORIZONTAL_MARGIN,
                bubble_y,
                author,
            )

        # === Рисуем пузырёк ===
        bubble_rect = QRectF(bubble_x, bubble_y, bubble_width, bubble_height)
        self._paint_bubble_background(painter, bubble_rect, is_own, option)

        # === Рисуем содержимое ===
        x = bubble_x + self.BUBBLE_PADDING_H
        y = bubble_y + self.BUBBLE_PADDING_V

        # Иконка закреплённого
        if is_pinned:
            painter.setFont(QFont(get_font_family("emoji"), 10))
            painter.setPen(self._color_accent)
            pin_x = bubble_x + bubble_width - 24
            painter.drawText(QPointF(pin_x, bubble_y + 14), "📌")

        # Forwarded
        if forwarded:
            painter.setFont(self._font_forwarded)
            painter.setPen(self._color_forwarded)
            fwd_name = forwarded.get("display_name", "")
            painter.drawText(
                QRectF(x, y, actual_content_width, 20),
                Qt.AlignLeft | Qt.AlignVCenter,
                f"↗ Переслано от {fwd_name}",
            )
            y += QFontMetrics(self._font_forwarded).height() + self.SPACING

        # Reply
        if reply_to:
            y = self._paint_reply(painter, x, y, actual_content_width, reply_to)
            y += self.SPACING

        # Author name (только чужие + показываем)
        if show_author and not is_own:
            painter.setFont(self._font_author)
            nick_color = QColor(author.get("nick_color", self._accent.hex))
            painter.setPen(nick_color)
            display_name = author.get("display_name", "Unknown")
            painter.drawText(
                QRectF(x, y, actual_content_width, 20),
                Qt.AlignLeft | Qt.AlignVCenter,
                display_name,
            )
            y += QFontMetrics(self._font_author).height() + self.SPACING

        # Deleted
        if is_deleted:
            painter.setFont(self._font_text)
            painter.setPen(self._color_deleted_text)
            painter.drawText(
                QRectF(x, y, actual_content_width, 20),
                Qt.AlignLeft | Qt.AlignVCenter,
                "🚫 Сообщение удалено",
            )
            y += QFontMetrics(self._font_text).height() + self.SPACING
        else:
            # Content text
            if content and msg_type == "text":
                msg_id = index.data(MessageRole.MessageId) or ""
                y = self._paint_text_content(painter, x, y, actual_content_width, content, msg_id)
                y += self.SPACING

            # File
            if file_att:
                y = self._paint_file_attachment(painter, x, y, actual_content_width, file_att)
                y += self.SPACING

            # Poll
            if poll and msg_type == "poll":
                y = self._paint_poll(painter, x, y, actual_content_width, poll)

        # Reactions
        if reactions:
            y = self._paint_reactions(painter, x, y, actual_content_width, reactions)

        # Timestamp + edited
        self._paint_timestamp(
            painter, x, y, actual_content_width,
            timestamp, is_edited, is_own,
        )

    # ========================
    # Sub-painters
    # ========================

    def _paint_bubble_background(
            self,
            painter: QPainter,
            rect: QRectF,
            is_own: bool,
            option: QStyleOptionViewItem,
    ) -> None:
        """Рисует фон пузырька с закруглёнными углами."""
        is_hovered = option.state & QStyle.State_MouseOver

        if is_own:
            bg_color = self._color_own_bg_hover if is_hovered else self._color_own_bg
        else:
            bg_color = self._color_other_bg_hover if is_hovered else self._color_other_bg

        path = QPainterPath()
        path.addRoundedRect(rect, self.BUBBLE_RADIUS, self.BUBBLE_RADIUS)

        painter.setPen(Qt.NoPen)
        painter.setBrush(bg_color)
        painter.drawPath(path)

    def _paint_avatar(
            self,
            painter: QPainter,
            x: int,
            y: int,
            author: dict,
    ) -> None:
        """Рисует аватар (круг с инициалом)."""
        size = self.AVATAR_SIZE
        rect = QRectF(x, y, size, size)

        # Круглый чёрный фон
        path = QPainterPath()
        path.addEllipse(rect)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#11111b"))
        painter.drawPath(path)

        # Буква
        display_name = author.get("display_name", "?")
        letter = display_name[0].upper() if display_name else "?"
        nick_color = QColor(author.get("nick_color", self._accent.hex))

        painter.setPen(nick_color)
        font = QFont(get_font_family("ui"), int(size * 0.4), QFont.Bold)
        painter.setFont(font)
        painter.drawText(rect.toRect(), Qt.AlignCenter, letter)

    def _paint_reply(
            self,
            painter: QPainter,
            x: float,
            y: float,
            max_width: float,
            reply: dict,
    ) -> float:
        """Рисует блок цитаты (reply)."""
        reply_height = self._calculate_reply_height(reply, int(max_width))

        # Фон
        reply_rect = QRectF(x, y, max_width, reply_height)
        path = QPainterPath()
        path.addRoundedRect(reply_rect, 4, 4)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._color_reply_bg)
        painter.drawPath(path)

        # Вертикальная полоска
        bar_rect = QRectF(x, y, self.REPLY_BAR_WIDTH, reply_height)
        path2 = QPainterPath()
        path2.addRoundedRect(bar_rect, 1.5, 1.5)
        painter.setBrush(self._color_accent)
        painter.drawPath(path2)

        inner_x = x + self.REPLY_BAR_WIDTH + self.REPLY_PADDING
        inner_y = y + self.REPLY_PADDING

        # Имя автора
        reply_author = reply.get("author", {})
        author_name = reply_author.get("display_name", "Unknown")
        author_color = QColor(reply_author.get("nick_color", self._accent.hex))

        painter.setFont(self._font_reply_author)
        painter.setPen(author_color)
        painter.drawText(
            QRectF(inner_x, inner_y, max_width - 20, 16),
            Qt.AlignLeft | Qt.AlignVCenter,
            author_name,
        )
        inner_y += QFontMetrics(self._font_reply_author).height() + 2

        # Текст
        if reply.get("is_deleted"):
            painter.setFont(self._font_reply_text)
            painter.setPen(self._color_deleted_text)
            painter.drawText(
                QRectF(inner_x, inner_y, max_width - 20, 16),
                Qt.AlignLeft | Qt.AlignVCenter,
                "Сообщение удалено",
            )
        else:
            reply_content = reply.get("content", "")
            if not reply_content:
                msg_type = reply.get("message_type", "text")
                if msg_type == "sticker":
                    reply_content = "🎨 Стикер"
                elif msg_type == "file":
                    reply_content = "📎 Файл"
                elif msg_type == "poll":
                    reply_content = "📊 Опрос"

            if len(reply_content) > 60:
                reply_content = reply_content[:60] + "..."

            painter.setFont(self._font_reply_text)
            painter.setPen(self._color_subtext)
            painter.drawText(
                QRectF(inner_x, inner_y, max_width - 20, 16),
                Qt.AlignLeft | Qt.AlignVCenter,
                reply_content,
            )

        return y + reply_height

    def _paint_text_content(
            self,
            painter: QPainter,
            x: float,
            y: float,
            max_width: float,
            text: str,
            msg_id: str = "",
    ) -> float:
        """
        Рисует текстовый контент с поддержкой markdown и блоков кода.

        Логика:
        - Разбиваем текст на сегменты (обычный текст / блок кода / инлайн-код)
        - Обычный текст рендерим через QTextDocument (он умеет markdown)
        - Блоки кода рисуем вручную через QPainter (полный контроль фона)
        - Инлайн-код идёт как часть обычного текста (без фона)
        """
        if not text:
            return y

        segments = self._parse_segments(text)

        current_y = y
        for seg in segments:
            if seg["type"] == "code_block":
                current_y = self._paint_code_block(
                    painter, x, current_y, max_width, seg["content"]
                )
                current_y += self.SPACING
            elif seg["type"] == "text":
                if seg["content"].strip() or seg["content"] == "\n":
                    current_y = self._paint_text_segment(
                        painter, x, current_y, max_width, seg["content"], msg_id
                    )

        return current_y

    # ========================
    # Segment Parsing
    # ========================

    def _parse_segments(self, text: str) -> list[dict]:
        """
        Разбивает сообщение на сегменты:
        - text: обычный текст (может содержать markdown и инлайн-код)
        - code_block: ```...```  — блок кода
        """
        import re

        segments = []
        # Ищем только блоки кода
        pattern = re.compile(r'```(.*?)```', re.DOTALL)

        last_end = 0
        for match in pattern.finditer(text):
            # Текст до блока кода
            if match.start() > last_end:
                segments.append({
                    "type": "text",
                    "content": text[last_end:match.start()],
                })

            segments.append({
                "type": "code_block",
                "content": match.group(1),
            })

            last_end = match.end()

        # Остаток после последнего блока кода
        if last_end < len(text):
            segments.append({
                "type": "text",
                "content": text[last_end:],
            })

        if not segments:
            segments.append({"type": "text", "content": text})

        return segments

    # ========================
    # Code Block Measurement
    # ========================

    def _measure_code_block(self, content: str, max_width: int) -> int:
        """
        Высота блока кода.
        Считаем по количеству строк с учётом переноса.
        """
        content = content.strip("\n")

        # Убираем метку языка (python, bash, ...) если она есть
        lines = content.split("\n")
        if lines and re.match(r'^[a-zA-Z0-9_+-]+$', lines[0].strip()) and len(lines) > 1:
            lines = lines[1:]
        content = "\n".join(lines).rstrip("\n")

        if not content:
            content = " "

        # Высота одной строки Fira Code
        fm = QFontMetrics(self._font_code)
        line_height = fm.height()
        line_spacing = 4
        padding_v = 12  # padding по вертикали

        # Считаем визуальные строки (с переносом длинных)
        visual_lines = 0
        inner_width = max_width - 32  # padding 16 с каждой стороны
        for line in content.split("\n"):
            if not line:
                visual_lines += 1
            else:
                # Сколько раз строка помещается в inner_width
                line_width = fm.horizontalAdvance(line)
                visual_lines += max(1, (line_width + inner_width - 1) // inner_width)

        return visual_lines * line_height + (visual_lines - 1) * line_spacing + padding_v * 2

    def _measure_text_segment(self, content: str, max_width: int) -> int:
        """Высота текстового сегмента через QTextDocument."""
        doc = QTextDocument()
        doc.setDefaultFont(self._font_text)
        doc.setTextWidth(max_width)
        html = self._markdown_to_html(content)
        doc.setHtml(f"<body>{html}</body>")
        return int(doc.size().height())

    # ========================
    # Painting
    # ========================

    def _paint_code_block(
            self,
            painter: QPainter,
            x: float,
            y: float,
            max_width: float,
            content: str,
    ) -> float:
        """
        Рисует блок кода: фон, скругление, текст через Fira Code.
        """
        content = content.strip("\n")

        # Убираем метку языка
        lines = content.split("\n")
        if lines and re.match(r'^[a-zA-Z0-9_+-]+$', lines[0].strip()) and len(lines) > 1:
            lines = lines[1:]
        content = "\n".join(lines).rstrip("\n")

        if not content:
            content = " "

        # Метрики
        fm = QFontMetrics(self._font_code)
        line_height = fm.height()
        line_spacing = 4
        padding_h = 16
        padding_v = 12

        # Считаем визуальные строки и общую высоту
        inner_width = max_width - padding_h * 2
        visual_lines_text = []
        for line in content.split("\n"):
            if not line:
                visual_lines_text.append("")
                continue
            # Разбиваем длинные строки
            if fm.horizontalAdvance(line) <= inner_width:
                visual_lines_text.append(line)
            else:
                # Разбиваем на части
                current = ""
                for ch in line:
                    if fm.horizontalAdvance(current + ch) > inner_width:
                        visual_lines_text.append(current)
                        current = ch
                    else:
                        current += ch
                if current:
                    visual_lines_text.append(current)

        block_height = (
            len(visual_lines_text) * line_height
            + (len(visual_lines_text) - 1) * line_spacing
            + padding_v * 2
        )

        # Фон блока
        block_rect = QRectF(x, y, max_width, block_height)
        path = QPainterPath()
        path.addRoundedRect(block_rect, 6, 6)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(self._palette.mantle))
        painter.drawPath(path)

        # Текст
        painter.setFont(self._font_code)
        painter.setPen(QColor(self._palette.text))

        text_y = y + padding_v + fm.ascent()
        for line in visual_lines_text:
            painter.drawText(QPointF(x + padding_h, text_y), line)
            text_y += line_height + line_spacing

        return y + block_height

    def _paint_text_segment(
            self,
            painter: QPainter,
            x: float,
            y: float,
            max_width: float,
            content: str,
            msg_id: str = "",
    ) -> float:
        """
        Рисует текстовый сегмент через QTextDocument.
        Кэширует по (msg_id, content_hash, width).
        """
        cache_key = f"{msg_id}_seg_{hash(content)}_{int(max_width)}"
        doc = self._doc_cache.get(cache_key)

        if doc is None:
            doc = QTextDocument()
            doc.setDefaultFont(self._font_text)
            doc.setTextWidth(max_width)

            html = self._markdown_to_html(content)
            doc.setDefaultStyleSheet(
                f"body {{ color: {self._color_text.name()}; }}"
            )
            doc.setHtml(f"<body>{html}</body>")

            if len(self._doc_cache) > 200:
                self._doc_cache.clear()
            self._doc_cache[cache_key] = doc

        painter.save()
        painter.translate(x, y)

        ctx = QAbstractTextDocumentLayout.PaintContext()
        ctx.palette.setColor(ctx.palette.Text, self._color_text)
        doc.documentLayout().draw(painter, ctx)

        painter.restore()

        return y + int(doc.size().height())

    def _paint_file_attachment(
            self,
            painter: QPainter,
            x: float,
            y: float,
            max_width: float,
            file_att: dict,
    ) -> float:
        """Рисует превью файла."""
        mime = file_att.get("mime_type", "")
        has_thumb = file_att.get("has_thumbnail", False)

        if has_thumb and mime.startswith("image/"):
            # Превью изображения (placeholder — серый прямоугольник)
            img_w = file_att.get("image_width", 320) or 320
            img_h = file_att.get("image_height", 240) or 240
            scale = min(self.IMAGE_MAX_WIDTH / img_w, self.IMAGE_MAX_HEIGHT / img_h, 1.0)
            display_w = int(img_w * scale)
            display_h = int(img_h * scale)

            img_rect = QRectF(x, y, display_w, display_h)
            path = QPainterPath()
            path.addRoundedRect(img_rect, 8, 8)
            painter.setPen(Qt.NoPen)
            painter.setBrush(self._color_file_bg)
            painter.drawPath(path)

            # Иконка по центру
            painter.setFont(QFont(get_font_family("emoji"), 28))
            painter.setPen(self._color_subtext)
            painter.drawText(img_rect.toRect(), Qt.AlignCenter, "🖼️")

            return y + display_h
        else:
            # Обычный файл
            file_rect = QRectF(x, y, max_width, self.FILE_PREVIEW_HEIGHT)
            path = QPainterPath()
            path.addRoundedRect(file_rect, 10, 10)
            painter.setPen(Qt.NoPen)
            painter.setBrush(self._color_file_bg)
            painter.drawPath(path)

            icon = get_file_icon(mime)
            filename = file_att.get("original_filename", "file")
            filesize = format_file_size(file_att.get("file_size", 0))

            # Иконка
            painter.setFont(QFont(get_font_family("emoji"), 22))
            painter.setPen(self._color_text)
            painter.drawText(QRectF(x + 10, y + 6, 40, 40), Qt.AlignCenter, icon)

            # Имя файла
            painter.setFont(self._font_file_name)
            painter.setPen(self._color_link)
            name_text = filename
            fm = QFontMetrics(self._font_file_name)
            available = int(max_width - 70)
            if fm.horizontalAdvance(name_text) > available:
                name_text = fm.elidedText(name_text, Qt.ElideMiddle, available)
            painter.drawText(
                QRectF(x + 56, y + 8, max_width - 66, 20),
                Qt.AlignLeft | Qt.AlignVCenter,
                name_text,
            )

            # Размер
            painter.setFont(self._font_file_size)
            painter.setPen(self._color_subtext)
            painter.drawText(
                QRectF(x + 56, y + 28, max_width - 66, 18),
                Qt.AlignLeft | Qt.AlignVCenter,
                filesize,
            )

            return y + self.FILE_PREVIEW_HEIGHT

    def _paint_poll(
            self,
            painter: QPainter,
            x: float,
            y: float,
            max_width: float,
            poll: dict,
    ) -> float:
        """Рисует опрос."""
        # Вопрос
        question = poll.get("question", "")
        painter.setFont(QFont(get_font_family("ui"), 15, QFont.DemiBold))
        painter.setPen(self._color_text)

        doc = QTextDocument()
        doc.setDefaultFont(QFont(get_font_family("ui"), 15, QFont.DemiBold))
        doc.setTextWidth(max_width)
        doc.setPlainText(question)
        q_height = int(doc.size().height())

        painter.save()
        painter.translate(x, y)
        ctx = QAbstractTextDocumentLayout.PaintContext()
        ctx.palette.setColor(ctx.palette.Text, self._color_text)
        doc.documentLayout().draw(painter, ctx)
        painter.restore()

        y += q_height + 8

        # Варианты
        options = poll.get("options", [])
        total_votes = poll.get("total_votes", 0)
        my_votes = poll.get("my_votes", [])

        for opt in options:
            opt_text = opt.get("text", "")
            vote_count = opt.get("vote_count", 0)
            percentage = opt.get("percentage", 0)
            is_selected = opt.get("id", "") in my_votes

            opt_height = 36

            # Фон варианта
            opt_rect = QRectF(x, y, max_width, opt_height)
            path = QPainterPath()
            path.addRoundedRect(opt_rect, 8, 8)
            painter.setPen(Qt.NoPen)

            if is_selected:
                painter.setBrush(self._color_reaction_active_bg)
            else:
                painter.setBrush(self._color_file_bg)
            painter.drawPath(path)

            # Прогресс-бар
            if total_votes > 0:
                progress_width = max_width * (percentage / 100)
                progress_rect = QRectF(x, y, progress_width, opt_height)
                progress_path = QPainterPath()
                progress_path.addRoundedRect(progress_rect, 8, 8)
                ar, ag, ab = self._accent.rgb
                painter.setBrush(QColor(ar, ag, ab, 25))
                painter.drawPath(progress_path)

            # Бордер если выбран
            if is_selected:
                painter.setPen(QPen(self._color_accent, 1.5))
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(opt_rect, 8, 8)

            # Текст варианта
            painter.setFont(self._font_text)
            painter.setPen(self._color_text)
            painter.drawText(
                QRectF(x + 12, y, max_width - 60, opt_height),
                Qt.AlignLeft | Qt.AlignVCenter,
                opt_text,
            )

            # Процент и количество
            if total_votes > 0:
                painter.setFont(self._font_file_size)
                painter.setPen(self._color_subtext)
                pct_text = f"{percentage:.0f}%"
                painter.drawText(
                    QRectF(x, y, max_width - 12, opt_height),
                    Qt.AlignRight | Qt.AlignVCenter,
                    pct_text,
                )

            y += opt_height + 4

        # Итого
        painter.setFont(self._font_file_size)
        painter.setPen(self._color_timestamp)
        total_text = f"Всего голосов: {total_votes}"
        if poll.get("is_anonymous"):
            total_text += " • Анонимный"
        painter.drawText(
            QRectF(x, y, max_width, 20),
            Qt.AlignLeft | Qt.AlignVCenter,
            total_text,
        )
        y += 20

        return y

    def _paint_reactions(
            self,
            painter: QPainter,
            x: float,
            y: float,
            max_width: float,
            reactions: list[dict],
    ) -> float:
        """Рисует полоску реакций."""
        rx = x
        for reaction in reactions:
            emoji = reaction.get("emoji", "")
            count = reaction.get("count", 0)
            users = reaction.get("users", [])
            is_mine = self._current_user_id in users

            text = f"{emoji} {count}" if count > 1 else emoji
            painter.setFont(self._font_reaction)
            fm = QFontMetrics(self._font_reaction)
            text_width = fm.horizontalAdvance(text) + 16  # Padding

            badge_rect = QRectF(rx, y, text_width, self.REACTION_HEIGHT)

            # Фон бейджа
            path = QPainterPath()
            path.addRoundedRect(badge_rect, 13, 13)
            painter.setPen(Qt.NoPen)

            if is_mine:
                painter.setBrush(self._color_reaction_active_bg)
            else:
                painter.setBrush(self._color_reaction_bg)
            painter.drawPath(path)

            # Бордер
            border_color = self._color_reaction_active_border if is_mine else self._color_reaction_border
            painter.setPen(QPen(border_color, 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(badge_rect, 13, 13)

            # Текст
            painter.setPen(self._color_text)
            painter.drawText(badge_rect.toRect(), Qt.AlignCenter, text)

            rx += text_width + 4

            # Перенос на следующую строку
            if rx + 60 > x + max_width:
                rx = x
                y += self.REACTION_HEIGHT + 4

        return y + self.REACTION_HEIGHT

    def _paint_timestamp(
            self,
            painter: QPainter,
            x: float,
            y: float,
            max_width: float,
            timestamp: str,
            is_edited: bool,
            is_own: bool,
    ) -> None:
        """Рисует временную метку и пометку (изменено)."""
        time_text = format_timestamp(timestamp)
        parts = []

        if is_edited:
            parts.append("изменено")

        parts.append(time_text)
        full_text = " • ".join(parts) if len(parts) > 1 else parts[0]

        painter.setFont(self._font_timestamp)
        painter.setPen(self._color_timestamp)

        alignment = Qt.AlignRight if is_own else Qt.AlignRight
        painter.drawText(
            QRectF(x, y, max_width, 16),
            alignment | Qt.AlignVCenter,
            full_text,
        )

    def _paint_sticker_message(
            self,
            painter: QPainter,
            rect: QRect,
            is_own: bool,
            sticker: dict,
            timestamp: str,
            top_offset: int,
    ) -> None:
        """Рисует стикер (без пузырька)."""
        size = self.STICKER_SIZE
        y = rect.top() + top_offset

        if is_own:
            x = rect.right() - size - self.HORIZONTAL_MARGIN
        else:
            x = rect.left() + self.HORIZONTAL_MARGIN + self.AVATAR_SIZE + self.AVATAR_MARGIN

        # Placeholder стикера
        sticker_rect = QRectF(x, y, size, size)
        path = QPainterPath()
        path.addRoundedRect(sticker_rect, 12, 12)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 10))
        painter.drawPath(path)

        painter.setFont(QFont(get_font_family("emoji"), 40))
        painter.setPen(self._color_text)
        painter.drawText(sticker_rect.toRect(), Qt.AlignCenter, "🎨")

        # Время под стикером
        painter.setFont(self._font_timestamp)
        painter.setPen(self._color_timestamp)
        time_text = format_timestamp(timestamp)
        time_y = y + size + 4
        painter.drawText(
            QRectF(x, time_y, size, 16),
            Qt.AlignRight | Qt.AlignVCenter,
            time_text,
        )

    # ========================
    # Content Width Calculation
    # ========================

    def _calculate_needed_width(
            self,
            content: str,
            msg_type: str,
            author: dict,
            show_author: bool,
            is_own: bool,
            reply_to, forwarded, reactions,
            file_att, poll,
            is_edited: bool,
            is_deleted: bool,
            timestamp: str,
            max_content_width: int,
    ) -> int:
        """Вычисляет нужную ширину контента (для адаптивных пузырьков)."""
        widths = []

        fm_text = QFontMetrics(self._font_text)
        fm_author = QFontMetrics(self._font_author)
        fm_ts = QFontMetrics(self._font_timestamp)

        # Author name
        if show_author and not is_own:
            name = author.get("display_name", "")
            widths.append(fm_author.horizontalAdvance(name))

        # Content
        if content and msg_type == "text":
            # Для коротких однострочных сообщений — ужимаем
            if "\n" not in content and fm_text.horizontalAdvance(content) < max_content_width:
                widths.append(fm_text.horizontalAdvance(content))
            else:
                widths.append(max_content_width)

        # Timestamp
        time_text = format_timestamp(timestamp)
        if is_edited:
            time_text = "изменено • " + time_text
        widths.append(fm_ts.horizontalAdvance(time_text) + 8)

        # File
        if file_att:
            widths.append(min(280, max_content_width))

        # Poll
        if poll:
            widths.append(max_content_width)

        # Reply
        if reply_to:
            widths.append(min(250, max_content_width))

        # Forwarded
        if forwarded:
            fwd_name = forwarded.get("display_name", "")
            fm_fwd = QFontMetrics(self._font_forwarded)
            widths.append(fm_fwd.horizontalAdvance(f"↗ Переслано от {fwd_name}"))

        # Deleted
        if is_deleted:
            widths.append(fm_text.horizontalAdvance("🚫 Сообщение удалено"))

        # Reactions
        if reactions:
            total_w = 0
            fm_react = QFontMetrics(self._font_reaction)
            for r in reactions:
                emoji = r.get("emoji", "")
                count = r.get("count", 0)
                text = f"{emoji} {count}" if count > 1 else emoji
                total_w += fm_react.horizontalAdvance(text) + 20
            widths.append(min(total_w, max_content_width))

        return max(widths) if widths else 120

    # ========================
    # Markdown to HTML
    # ========================

    def _markdown_to_html(self, text: str) -> str:
        """
        Конвертирует markdown в HTML.

        Поддержка:
        - **жирный** → <b>жирный</b>
        - *курсив* → <i>курсив</i>
        - __подчёркнутый__ → <u>подчёркнутый</u>
        - ~~зачёркнутый~~ → <s>зачёркнутый</s>
        - ||спойлер|| → <span style="background:...">спойлер</span>
        - `инлайн-код` → <code style="font-family: Fira Code">инлайн-код</code>

        ВАЖНО: инлайн-код обрабатывается ДО html.escape, чтобы не экранировать
        наш собственный HTML. Остальной текст экранируется после.
        """
        import html as html_module

        # 1. Вырезаем инлайн-код ПЛЕЙСХОЛДЕРАМИ (до escape)
        code_store: list[str] = []

        def stash_code(match):
            idx = len(code_store)
            code_store.append(match.group(1))
            return f"\x00CODE{idx}\x00"

        text = re.sub(r'`([^`\n]+)`', stash_code, text)

        # 2. Экранируем HTML (но плейсхолдеры \x00 не тронуты)
        text = html_module.escape(text)

        # 3. Обрабатываем остальную markdown-разметку
        text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
        text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
        text = re.sub(r'__(.+?)__', r'<u>\1</u>', text)
        text = re.sub(r'~~(.+?)~~', r'<s>\1</s>', text)
        text = re.sub(
            r'\|\|(.+?)\|\|',
            lambda m: (
                f'<span style="background-color: {self._palette.surface2}; '
                f'color: {self._palette.surface2}; '
                f'border-radius: 4px; padding: 0 4px;">{m.group(1)}</span>'
            ),
            text,
        )

        # 4. Возвращаем инлайн-код как готовый HTML
        code_family = self._font_code.family()
        code_size = self._font_code.pointSize()
        for idx, code_content in enumerate(code_store):
            safe_code = html_module.escape(code_content)
            replacement = (
                f'<code style="font-family: {code_family}, monospace; '
                f'font-size: {code_size}pt; '
                f'background-color: {self._palette.surface0}; '
                f'padding: 1px 5px;">'
                f'{safe_code}</code>'
            )
            text = text.replace(f"\x00CODE{idx}\x00", replacement)

        # 5. Переносы строк
        text = text.replace('\n', '<br>')

        return text
