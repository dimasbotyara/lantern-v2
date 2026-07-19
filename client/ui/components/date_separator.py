"""
Lantern v2 — Date Separator & Unread Separator
Горизонтальные разделители для чата: "── Сегодня ──", "── Непрочитанные ──"
"""

from typing import Optional

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QFrame
from PyQt5.QtCore import Qt, QSize


class DateSeparator(QWidget):
    """
    Разделитель дат в чате.

    Выглядит как:
    ─────────── Сегодня ───────────
    ─────────── 28 мая ────────────
    """

    def __init__(self, text: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("dateSeparator")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(40, 8, 40, 4)
        layout.setSpacing(12)

        # Левая линия
        left_line = QFrame()
        left_line.setObjectName("dateSeparatorLine")
        left_line.setFrameShape(QFrame.HLine)
        left_line.setSizePolicy(left_line.sizePolicy().horizontalPolicy(),
                                left_line.sizePolicy().verticalPolicy())
        layout.addWidget(left_line, 1)

        # Текст
        label = QLabel(text)
        label.setObjectName("dateSeparatorText")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label, 0)

        # Правая линия
        right_line = QFrame()
        right_line.setObjectName("dateSeparatorLine")
        right_line.setFrameShape(QFrame.HLine)
        layout.addWidget(right_line, 1)

    def sizeHint(self) -> QSize:
        return QSize(400, 40)


class UnreadSeparator(QWidget):
    """
    Разделитель непрочитанных сообщений.

    Выглядит как:
    ──────── Непрочитанные сообщения ────────
    (красная линия и красный бейдж)
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("unreadSeparator")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(40, 4, 40, 4)
        layout.setSpacing(12)

        # Левая линия
        left_line = QFrame()
        left_line.setObjectName("unreadSeparatorLine")
        left_line.setFrameShape(QFrame.HLine)
        layout.addWidget(left_line, 1)

        # Текст
        label = QLabel("Непрочитанные сообщения")
        label.setObjectName("unreadSeparatorText")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label, 0)

        # Правая линия
        right_line = QFrame()
        right_line.setObjectName("unreadSeparatorLine")
        right_line.setFrameShape(QFrame.HLine)
        layout.addWidget(right_line, 1)

    def sizeHint(self) -> QSize:
        return QSize(400, 32)