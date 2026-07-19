"""
Lantern v2 — Forward Dialog
Диалог выбора чата для пересылки сообщений.
"""

from typing import Optional

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget,
    QListWidgetItem, QLabel, QPushButton, QLineEdit,
    QWidget
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt, pyqtSignal, QSize

from client.ui.components.avatar import AvatarWidget
from client.themes.catppuccin import Palette, AccentColor


class ForwardDialog(QDialog):
    """
    Диалог пересылки сообщений.

    Показывает список чатов, позволяет выбрать целевой.
    """

    chat_selected = pyqtSignal(str)  # target_chat_id

    def __init__(
        self,
        chats: list[dict],
        palette: Palette,
        accent: AccentColor,
        message_count: int = 1,
        current_user_id: str = "",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("↗️ Переслать сообщение")
        self.setMinimumSize(380, 460)
        self.setModal(True)

        self._chats = chats
        self._palette = palette
        self._accent = accent
        self._current_user_id = current_user_id

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Заголовок
        title = QLabel(f"Переслать {'сообщение' if message_count == 1 else f'{message_count} сообщений'}")
        title.setObjectName("dialogTitle")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Поиск
        self._search = QLineEdit()
        self._search.setPlaceholderText("🔍 Поиск чата...")
        self._search.textChanged.connect(self._on_search)
        layout.addWidget(self._search)

        # Список чатов
        self._list = QListWidget()
        self._list.setSpacing(2)
        self._list.itemDoubleClicked.connect(self._on_select)
        layout.addWidget(self._list, 1)

        self._render_chats(chats)

        # Кнопки
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Отмена")
        cancel_btn.setObjectName("secondaryButton")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        send_btn = QPushButton("↗️ Переслать")
        send_btn.setCursor(Qt.PointingHandCursor)
        send_btn.clicked.connect(self._on_forward)
        btn_row.addWidget(send_btn)

        layout.addLayout(btn_row)

    def _render_chats(self, chats: list[dict]) -> None:
        self._list.clear()
        for chat in chats:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, chat.get("id"))
            item.setSizeHint(QSize(0, 52))

            name = chat.get("name", "Chat")
            chat_type = chat.get("chat_type", "general")
            icon = "#️⃣" if chat_type == "general" else "👤"

            widget = QWidget()
            row = QHBoxLayout(widget)
            row.setContentsMargins(8, 4, 8, 4)
            row.setSpacing(10)

            avatar = AvatarWidget(size="small", show_status=False)
            if chat_type == "general":
                avatar.set_initials("#", self._accent.hex)
            else:
                avatar.set_initials(name or "?", self._accent.hex)
            row.addWidget(avatar)

            label = QLabel(f"{icon} {name}")
            label.setFont(QFont("Segoe UI", 13))
            row.addWidget(label, 1)

            self._list.addItem(item)
            self._list.setItemWidget(item, widget)

    def _on_search(self, query: str) -> None:
        q = query.strip().lower()
        if not q:
            self._render_chats(self._chats)
        else:
            filtered = [c for c in self._chats if q in (c.get("name") or "").lower()]
            self._render_chats(filtered)

    def _on_select(self, item: QListWidgetItem) -> None:
        chat_id = item.data(Qt.UserRole)
        if chat_id:
            self.chat_selected.emit(chat_id)
            self.accept()

    def _on_forward(self) -> None:
        item = self._list.currentItem()
        if item:
            self._on_select(item)