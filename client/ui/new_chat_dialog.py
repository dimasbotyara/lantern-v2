"""
Lantern v2 — New Chat Dialog
Диалог создания нового личного чата.
Показывает список всех пользователей сервера.
"""

from typing import Optional

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget,
    QListWidgetItem, QLabel, QPushButton, QLineEdit, QWidget
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt, pyqtSignal, QSize

from client.ui.components.avatar import AvatarWidget
from client.themes.catppuccin import Palette, AccentColor
from client.utils.helpers import status_to_display


class NewChatDialog(QDialog):
    """Диалог создания личного чата."""

    user_selected = pyqtSignal(str)  # target_user_id

    def __init__(
        self,
        users: list[dict],
        current_user_id: str,
        palette: Palette,
        accent: AccentColor,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("✚ Новый чат")
        self.setMinimumSize(380, 460)
        self.setModal(True)

        self._users = [u for u in users if u.get("id") != current_user_id]
        self._palette = palette
        self._accent = accent

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel("Начать личный чат")
        title.setObjectName("dialogTitle")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        self._search = QLineEdit()
        self._search.setPlaceholderText("🔍 Поиск пользователей...")
        self._search.textChanged.connect(self._on_search)
        layout.addWidget(self._search)

        self._list = QListWidget()
        self._list.setSpacing(2)
        self._list.itemDoubleClicked.connect(self._on_select)
        layout.addWidget(self._list, 1)

        self._render_users(self._users)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Отмена")
        cancel_btn.setObjectName("secondaryButton")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        start_btn = QPushButton("💬 Начать чат")
        start_btn.setCursor(Qt.PointingHandCursor)
        start_btn.clicked.connect(self._on_start)
        btn_row.addWidget(start_btn)

        layout.addLayout(btn_row)

    def _render_users(self, users: list[dict]) -> None:
        self._list.clear()
        for user in users:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, user.get("id"))
            item.setSizeHint(QSize(0, 52))

            widget = QWidget()
            row = QHBoxLayout(widget)
            row.setContentsMargins(8, 4, 8, 4)
            row.setSpacing(10)

            avatar = AvatarWidget(size="small", show_status=True)
            display_name = user.get("display_name", "?")
            nick_color = user.get("nick_color", self._accent.hex)
            avatar.set_initials(display_name, nick_color)
            avatar.set_status(user.get("status", "offline"))
            row.addWidget(avatar)

            info = QVBoxLayout()
            info.setSpacing(0)
            name = QLabel(display_name)
            name.setFont(QFont("Segoe UI", 13, QFont.DemiBold))
            name.setStyleSheet(f"color: {nick_color};")
            info.addWidget(name)

            status_text, _ = status_to_display(user.get("status", "offline"))
            status_label = QLabel(status_text)
            status_label.setObjectName("subtitleLabel")
            info.addWidget(status_label)

            row.addLayout(info, 1)

            self._list.addItem(item)
            self._list.setItemWidget(item, widget)

    def _on_search(self, query: str) -> None:
        q = query.strip().lower()
        if not q:
            self._render_users(self._users)
        else:
            filtered = [
                u for u in self._users
                if q in u.get("display_name", "").lower()
                or q in u.get("username", "").lower()
            ]
            self._render_users(filtered)

    def _on_select(self, item: QListWidgetItem) -> None:
        uid = item.data(Qt.UserRole)
        if uid:
            self.user_selected.emit(uid)
            self.accept()

    def _on_start(self) -> None:
        item = self._list.currentItem()
        if item:
            self._on_select(item)