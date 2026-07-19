"""
Lantern v2 — Reply Preview Widget
Превью ответа: над полем ввода и внутри пузырька сообщения.
"""

from typing import Optional

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton
)
from PyQt5.QtCore import Qt, QSize, pyqtSignal


class ReplyPreviewBar(QWidget):
    """
    Превью ответа над полем ввода.

    ┌─────────────────────────────────────────┐
    │ ┃ ↩ Ответ для Alice                  ✕ │
    │ ┃ Привет! Как дела у тебя сегодня...    │
    └─────────────────────────────────────────┘
    """

    close_requested = pyqtSignal()
    clicked = pyqtSignal()  # Клик → скролл к оригиналу

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("replyPreviewBar")
        self.setVisible(False)
        self.setCursor(Qt.PointingHandCursor)

        self._message_id: Optional[str] = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Текстовая часть
        text_layout = QVBoxLayout()
        text_layout.setSpacing(1)

        self._author_label = QLabel()
        self._author_label.setObjectName("replyPreviewAuthor")
        text_layout.addWidget(self._author_label)

        self._text_label = QLabel()
        self._text_label.setObjectName("replyPreviewText")
        self._text_label.setWordWrap(False)
        text_layout.addWidget(self._text_label)

        layout.addLayout(text_layout, 1)

        # Кнопка закрытия
        close_btn = QPushButton("✕")
        close_btn.setObjectName("replyCloseButton")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self._on_close)
        layout.addWidget(close_btn)

    def set_reply(
            self,
            message_id: str,
            author_name: str,
            author_color: str,
            content: str,
            message_type: str = "text",
    ) -> None:
        """
        Устанавливает данные для превью ответа.

        Args:
            message_id: ID оригинального сообщения.
            author_name: Имя автора.
            author_color: Цвет ника автора.
            content: Текст сообщения (обрезается).
            message_type: Тип сообщения.
        """
        self._message_id = message_id

        self._author_label.setText(f"↩ Ответ для {author_name}")
        self._author_label.setStyleSheet(f"color: {author_color};")

        # Формируем текст превью
        if message_type == "sticker":
            preview_text = "🎨 Стикер"
        elif message_type == "poll":
            preview_text = "📊 Опрос"
        elif message_type == "file":
            preview_text = f"📎 {content}" if content else "📎 Файл"
        else:
            preview_text = content or ""

        # Обрезаем
        if len(preview_text) > 80:
            preview_text = preview_text[:80] + "..."

        self._text_label.setText(preview_text)
        self.setVisible(True)

    def clear(self) -> None:
        """Очищает превью и скрывает."""
        self._message_id = None
        self._author_label.setText("")
        self._text_label.setText("")
        self.setVisible(False)

    @property
    def reply_message_id(self) -> Optional[str]:
        """ID сообщения, на которое отвечаем."""
        return self._message_id

    @property
    def is_active(self) -> bool:
        """Активен ли режим ответа."""
        return self._message_id is not None

    def _on_close(self) -> None:
        """Закрытие превью."""
        self.clear()
        self.close_requested.emit()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._message_id:
            self.clicked.emit()


class ReplyInBubble(QWidget):
    """
    Мини-цитата внутри пузырька сообщения.

    ┃ Alice
    ┃ Привет! Как дела...
    """

    clicked = pyqtSignal(str)  # message_id → скролл к оригиналу

    def __init__(
            self,
            message_id: str,
            author_name: str,
            author_color: str,
            content: Optional[str],
            is_deleted: bool = False,
            message_type: str = "text",
            parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setObjectName("replyInBubble")
        self.setCursor(Qt.PointingHandCursor)

        self._message_id = message_id

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)

        # Автор
        author_label = QLabel(author_name)
        author_label.setObjectName("replyInBubbleAuthor")
        author_label.setStyleSheet(f"color: {author_color};")
        layout.addWidget(author_label)

        # Текст
        if is_deleted:
            text_label = QLabel("Сообщение удалено")
            text_label.setObjectName("replyDeletedText")
        else:
            if message_type == "sticker":
                display_text = "🎨 Стикер"
            elif message_type == "poll":
                display_text = "📊 Опрос"
            elif message_type == "file":
                display_text = f"📎 {content}" if content else "📎 Файл"
            else:
                display_text = content or ""

            if len(display_text) > 60:
                display_text = display_text[:60] + "..."

            text_label = QLabel(display_text)
            text_label.setObjectName("replyInBubbleText")

        text_label.setWordWrap(False)
        layout.addWidget(text_label)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._message_id)

    def sizeHint(self) -> QSize:
        return QSize(200, 36)