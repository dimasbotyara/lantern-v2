"""
Lantern v2 — Chat List Sidebar
Левая панель с:
- Профилем пользователя (аватар + ник + статус)
- Поиском по чатам
- Списком чатов (general + direct)
- Кнопкой нового чата
- Кнопкой настроек
"""

from typing import Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
    QListWidgetItem, QLabel, QPushButton, QLineEdit,
    QFrame, QMenu, QAction, QSizePolicy, QAbstractItemView
)
from PyQt5.QtGui import (
    QFont, QColor, QPainter, QPainterPath, QPixmap, QIcon, QCursor
)
from PyQt5.QtCore import (
    Qt, QSize, pyqtSignal, QTimer, QPoint
)

from client.ui.components.avatar import AvatarWidget
from client.themes.fonts import get_font_family
from client.themes.catppuccin import Palette, AccentColor
from client.utils.helpers import (
    format_timestamp, truncate_text, status_to_display
)


class ChatListSidebar(QWidget):
    """
    Сайдбар со списком чатов.

    Сигналы:
        chat_selected(str): chat_id
        new_chat_requested(): открыть диалог создания чата
        settings_requested(): открыть настройки
        status_change_requested(str): новый статус
        profile_requested(): открыть свой профиль
    """

    chat_selected = pyqtSignal(str)
    new_chat_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    status_change_requested = pyqtSignal(str)
    profile_requested = pyqtSignal()

    def __init__(
        self,
        palette: Palette,
        accent: AccentColor,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setMinimumWidth(280)
        self.setMaximumWidth(380)

        self._palette = palette
        self._accent = accent
        self._current_user: Optional[dict] = None
        self._chats: list[dict] = []
        self._selected_chat_id: Optional[str] = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Строит UI сайдбара."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # === Header (профиль) ===
        header = QWidget()
        header.setObjectName("sidebarHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 8, 12, 8)
        header_layout.setSpacing(10)

        self._user_avatar = AvatarWidget(size="medium", show_status=True)
        self._user_avatar.clicked.connect(self.profile_requested.emit)
        header_layout.addWidget(self._user_avatar)

        user_info = QVBoxLayout()
        user_info.setSpacing(1)

        self._user_name_label = QLabel("Lantern v2")
        self._user_name_label.setObjectName("chatItemName")
        self._user_name_label.setFont(QFont(get_font_family("ui"), 14, QFont.DemiBold))
        user_info.addWidget(self._user_name_label)

        self._user_status_label = QLabel("Не подключено")
        self._user_status_label.setObjectName("subtitleLabel")
        user_info.addWidget(self._user_status_label)

        header_layout.addLayout(user_info, 1)

        # Кнопка статуса (меню)
        self._status_btn = QPushButton("●")
        self._status_btn.setObjectName("iconButton")
        self._status_btn.setCursor(Qt.PointingHandCursor)
        self._status_btn.setToolTip("Изменить статус")
        self._status_btn.setFixedSize(32, 32)
        self._status_btn.clicked.connect(self._show_status_menu)
        header_layout.addWidget(self._status_btn)

        layout.addWidget(header)

        # === Разделитель ===
        sep = QFrame()
        sep.setObjectName("separator")
        sep.setFrameShape(QFrame.HLine)
        layout.addWidget(sep)

        # === Поиск + Новый чат ===
        search_row = QHBoxLayout()
        search_row.setContentsMargins(12, 8, 12, 8)
        search_row.setSpacing(8)

        self._search_input = QLineEdit()
        self._search_input.setObjectName("searchInput")
        self._search_input.setPlaceholderText("🔍 Поиск чатов...")
        self._search_input.textChanged.connect(self._on_search)
        search_row.addWidget(self._search_input, 1)

        self._new_chat_btn = QPushButton("✚")
        self._new_chat_btn.setObjectName("iconButton")
        self._new_chat_btn.setCursor(Qt.PointingHandCursor)
        self._new_chat_btn.setToolTip("Новый чат")
        self._new_chat_btn.setFont(QFont(get_font_family("ui"), 16))
        self._new_chat_btn.setFixedSize(36, 36)
        self._new_chat_btn.clicked.connect(self.new_chat_requested.emit)
        search_row.addWidget(self._new_chat_btn)

        layout.addLayout(search_row)

        # === Список чатов ===
        self._chat_list = QListWidget()
        self._chat_list.setObjectName("chatList")
        self._chat_list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self._chat_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._chat_list.setFocusPolicy(Qt.NoFocus)
        self._chat_list.itemClicked.connect(self._on_chat_clicked)

        layout.addWidget(self._chat_list, 1)

        # === Footer (настройки) ===
        footer = QWidget()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(12, 6, 12, 8)
        footer_layout.setSpacing(8)

        self._settings_btn = QPushButton("⚙️ Настройки")
        self._settings_btn.setObjectName("ghostButton")
        self._settings_btn.setCursor(Qt.PointingHandCursor)
        self._settings_btn.setFont(QFont(get_font_family("ui"), 13))
        self._settings_btn.clicked.connect(self.settings_requested.emit)
        footer_layout.addWidget(self._settings_btn)

        footer_layout.addStretch()

        layout.addWidget(footer)

    # ========================
    # Public API
    # ========================

    def set_current_user(self, user_data: dict) -> None:
        """Устанавливает текущего пользователя."""
        self._current_user = user_data

        display_name = user_data.get("display_name", "User")
        nick_color = user_data.get("nick_color", self._accent.hex)
        status = user_data.get("status", "online")

        self._user_name_label.setText(display_name)
        self._user_name_label.setStyleSheet(f"color: {nick_color};")

        status_text, _ = status_to_display(status)
        self._user_status_label.setText(status_text)

        # Аватар
        avatar_path = user_data.get("avatar_path")
        if avatar_path:
            pixmap = QPixmap(avatar_path)
            if not pixmap.isNull():
                self._user_avatar.set_image(pixmap)
            else:
                self._user_avatar.set_initials(display_name, nick_color)
        else:
            self._user_avatar.set_initials(display_name, nick_color)

        self._user_avatar.set_status(status)

    def set_chats(self, chats: list[dict]) -> None:
        """Загружает список чатов."""
        self._chats = chats
        self._render_chats(chats)

    def update_chat(self, chat_data: dict) -> None:
        """Обновляет один чат в списке (новое сообщение, unread и т.д.)."""
        chat_id = chat_data.get("id")

        # Ищем существующий
        found = False
        for i, chat in enumerate(self._chats):
            if chat.get("id") == chat_id:
                self._chats[i] = chat_data
                found = True
                break

        if not found:
            # Новый чат (кто-то написал первый)
            self._chats.insert(0, chat_data)
        else:
            # Пересортировка: чат с новым сообщением — наверх
            self._chats.sort(
                key=lambda c: c.get("last_message", {}).get("created_at", "") if c.get("last_message") else "",
                reverse=True,
            )

        self._render_chats(self._chats)

    def add_chat(self, chat_data: dict) -> None:
        """Добавляет новый чат (при создании direct)."""
        # Проверяем дубликат
        for chat in self._chats:
            if chat.get("id") == chat_data.get("id"):
                return

        self._chats.insert(0, chat_data)
        self._render_chats(self._chats)

    def set_selected_chat(self, chat_id: str) -> None:
        """Подсвечивает выбранный чат."""
        self._selected_chat_id = chat_id
        for i in range(self._chat_list.count()):
            item = self._chat_list.item(i)
            if item.data(Qt.UserRole) == chat_id:
                self._chat_list.setCurrentItem(item)
                break

    def update_user_status(self, user_id: str, status: str) -> None:
        """Обновляет статус пользователя в чатах."""
        if self._current_user and self._current_user.get("id") == user_id:
            status_text, _ = status_to_display(status)
            self._user_status_label.setText(status_text)
            self._user_avatar.set_status(status)

        # Обновляем в списке чатов
        for chat in self._chats:
            if chat.get("chat_type") == "direct":
                for member in chat.get("members", []):
                    if member.get("id") == user_id:
                        member["status"] = status

        self._render_chats(self._chats)

    def set_theme(self, palette: Palette, accent: AccentColor) -> None:
        """Обновляет тему."""
        self._palette = palette
        self._accent = accent
        self._render_chats(self._chats)

    # ========================
    # Rendering
    # ========================

    def _render_chats(self, chats: list[dict]) -> None:
        """Отрисовывает список чатов."""
        self._chat_list.clear()

        for chat in chats:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, chat.get("id"))
            item.setSizeHint(QSize(0, 68))

            widget = self._create_chat_item_widget(chat)
            self._chat_list.addItem(item)
            self._chat_list.setItemWidget(item, widget)

        # Восстанавливаем выбор
        if self._selected_chat_id:
            self.set_selected_chat(self._selected_chat_id)

    def _create_chat_item_widget(self, chat: dict) -> QWidget:
        """Создаёт виджет одного элемента списка чатов."""
        widget = QWidget()
        widget.setObjectName("chatListItem")
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(10)

        # Аватар
        avatar = AvatarWidget(size="medium", show_status=True)
        chat_type = chat.get("chat_type", "general")
        chat_name = chat.get("name", "Chat")
        members = chat.get("members", [])

        if chat_type == "general":
            avatar.set_initials("#", self._accent.hex)
            avatar.set_status("online")
        elif chat_type == "direct" and members:
            # Находим собеседника
            other = None
            current_id = self._current_user.get("id") if self._current_user else ""
            for m in members:
                if m.get("id") != current_id:
                    other = m
                    break

            if other:
                nick_color = other.get("nick_color", self._accent.hex)
                avatar.set_initials(other.get("display_name", "?"), nick_color)
                avatar.set_status(other.get("status", "offline"))
            else:
                avatar.set_initials(chat_name, self._accent.hex)
        else:
            avatar.set_initials(chat_name, self._accent.hex)

        layout.addWidget(avatar)

        # Текст
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)

        # Верхняя строка: имя + время
        top_row = QHBoxLayout()
        top_row.setSpacing(4)

        name_label = QLabel(chat_name or "Chat")
        name_label.setObjectName("chatItemName")
        name_label.setFont(QFont(get_font_family("ui"), 13, QFont.DemiBold))
        top_row.addWidget(name_label, 1)

        # Время последнего сообщения
        last_msg = chat.get("last_message")
        if last_msg:
            time_text = format_timestamp(last_msg.get("created_at"), show_date=True)
            time_label = QLabel(time_text)
            time_label.setObjectName("chatItemTime")
            top_row.addWidget(time_label)

        text_layout.addLayout(top_row)

        # Нижняя строка: превью + бейдж
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(4)

        preview_text = ""
        if last_msg:
            author = last_msg.get("author", {})
            author_name = author.get("display_name", "")
            content = last_msg.get("content", "")
            msg_type = last_msg.get("message_type", "text")

            if msg_type == "sticker":
                content = "🎨 Стикер"
            elif msg_type == "poll":
                content = "📊 Опрос"
            elif msg_type == "file":
                content = "📎 Файл"

            if chat_type == "general":
                preview_text = f"{author_name}: {content}" if content else f"{author_name}"
            else:
                preview_text = content or ""

            preview_text = truncate_text(preview_text, 40)

        preview_label = QLabel(preview_text or "Нет сообщений")
        preview_label.setObjectName("chatItemPreview")
        bottom_row.addWidget(preview_label, 1)

        # Бейдж непрочитанных
        unread = chat.get("unread_count", 0)
        if unread > 0:
            badge_text = str(unread) if unread < 100 else "99+"
            badge = QLabel(badge_text)
            badge.setObjectName("unreadBadge")
            badge.setAlignment(Qt.AlignCenter)
            badge.setFixedHeight(20)
            badge.setMinimumWidth(20)
            bottom_row.addWidget(badge)

        text_layout.addLayout(bottom_row)
        layout.addLayout(text_layout, 1)

        return widget

    # ========================
    # Events
    # ========================

    def _on_chat_clicked(self, item: QListWidgetItem) -> None:
        """Обработка клика по чату."""
        chat_id = item.data(Qt.UserRole)
        if chat_id:
            self._selected_chat_id = chat_id
            self.chat_selected.emit(chat_id)

    def _on_search(self, query: str) -> None:
        """Фильтрация чатов по поиску."""
        query = query.strip().lower()

        if not query:
            self._render_chats(self._chats)
            return

        filtered = [
            chat for chat in self._chats
            if query in (chat.get("name") or "").lower()
        ]
        self._render_chats(filtered)

    def _show_status_menu(self) -> None:
        """Показывает меню выбора статуса."""
        menu = QMenu(self)

        statuses = [
            ("🟢", "В сети", "online"),
            ("🟡", "Отошёл", "away"),
            ("🔴", "Не беспокоить", "do_not_disturb"),
            ("⚫", "Невидимка", "invisible"),
        ]

        for emoji, text, status_value in statuses:
            action = QAction(f"{emoji}  {text}", menu)
            action.setFont(QFont(get_font_family("ui"), 13))
            action.triggered.connect(
                lambda checked, s=status_value: self.status_change_requested.emit(s)
            )
            menu.addAction(action)

        menu.popup(QCursor.pos())