"""
Lantern v2 — Client Entry Point
Главное окно приложения. Связывает все компоненты.
"""

import sys
import asyncio
import json
from typing import Optional
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout,
    QVBoxLayout, QStackedWidget, QSplitter, QFileDialog,
    QSystemTrayIcon, QMenu, QAction, QLabel, QMessageBox
)
from PyQt5.QtGui import QIcon, QFont, QPixmap, QCloseEvent
from PyQt5.QtCore import Qt, QSize, QTimer, pyqtSignal, QSettings

import qasync

from client.config import ClientConfig, AuthTokenStorage, CONFIG_DIR
from client.themes.catppuccin import get_palette, PALETTES
from client.themes.stylesheet import generate_stylesheet
from client.network.api_client import api_client
from client.network.ws_client import ws_client, WSCallbacks, WSState
from client.network.file_transfer import file_transfer_manager

from client.ui.login_widget import LoginWidget
from client.ui.chat_list import ChatListSidebar
from client.ui.chat_view import ChatView
from client.ui.message_input import MessageInput
from client.ui.settings_dialog import SettingsDialog
from client.ui.forward_dialog import ForwardDialog
from client.ui.poll_dialog import PollDialog
from client.ui.new_chat_dialog import NewChatDialog
from client.ui.components.emoji_picker import EmojiPicker
from client.ui.components.connection_bar import ConnectionBar
from client.ui.components.notification import ToastNotification, send_system_notification


class MainWindow(QMainWindow):
    """Главное окно Lantern v2."""

    def __init__(self):
        super().__init__()

        self._config = ClientConfig.load()
        self._tokens = AuthTokenStorage()
        self._current_user: Optional[dict] = None
        self._current_chat_id: Optional[str] = None
        self._chats: list[dict] = []
        self._all_users: list[dict] = []
        self._emoji_picker: Optional[EmojiPicker] = None

        # Тема
        self._palette = get_palette(self._config.theme.palette)
        self._accent = self._palette.get_accent(self._config.theme.accent_color)

        self._setup_window()
        self._setup_ui()
        self._setup_tray()
        self._apply_theme()
        self._setup_ws_callbacks()

        # Автоподключение
        QTimer.singleShot(100, self._try_auto_connect)

    def _setup_window(self) -> None:
        self.setWindowTitle("🏮 Lantern v2")
        self.setMinimumSize(900, 600)

        # Восстанавливаем геометрию
        settings = QSettings("Lantern", "v2")
        geometry = settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            self.resize(1100, 700)

        state = settings.value("windowState")
        if state:
            self.restoreState(state)

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        self._main_layout = QVBoxLayout(central)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(0)

        # Stacked: login / main
        self._stack = QStackedWidget()
        self._main_layout.addWidget(self._stack, 1)

        # === Login Page ===
        self._login_widget = LoginWidget(self._palette, self._accent)
        self._login_widget.login_requested.connect(self._on_login)
        self._login_widget.register_requested.connect(self._on_register)
        self._login_widget.server_selected.connect(self._on_server_selected)
        self._login_widget.manual_connect_requested.connect(self._on_manual_connect)
        self._stack.addWidget(self._login_widget)

        # === Main Chat Page ===
        main_page = QWidget()
        main_page_layout = QVBoxLayout(main_page)
        main_page_layout.setContentsMargins(0, 0, 0, 0)
        main_page_layout.setSpacing(0)

        # Splitter: sidebar | chat
        self._splitter = QSplitter(Qt.Horizontal)

        # Sidebar
        self._sidebar = ChatListSidebar(self._palette, self._accent)
        self._sidebar.chat_selected.connect(self._on_chat_selected)
        self._sidebar.new_chat_requested.connect(self._on_new_chat)
        self._sidebar.settings_requested.connect(self._on_settings)
        self._sidebar.status_change_requested.connect(self._on_status_change)
        self._splitter.addWidget(self._sidebar)

        # Chat area
        chat_container = QWidget()
        chat_layout = QVBoxLayout(chat_container)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(0)

        # Empty state
        self._empty_state = QWidget()
        empty_layout = QVBoxLayout(self._empty_state)
        empty_layout.setAlignment(Qt.AlignCenter)

        logo = QLabel("🏮")
        logo.setFont(QFont("Segoe UI Emoji", 64))
        logo.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(logo)

        title = QLabel("Lantern v2")
        title.setObjectName("appTitle")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("Segoe UI", 28, QFont.Bold))
        empty_layout.addWidget(title)

        subtitle = QLabel("Выберите чат, чтобы начать общение")
        subtitle.setObjectName("subtitleLabel")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setFont(QFont("Segoe UI", 14))
        empty_layout.addWidget(subtitle)

        credit = QLabel("Made by dimasbotyara")
        credit.setObjectName("mutedLabel")
        credit.setAlignment(Qt.AlignCenter)
        credit.setFont(QFont("Segoe UI", 11))
        empty_layout.addSpacing(20)
        empty_layout.addWidget(credit)

        # Chat content (stacked: empty / chat)
        self._chat_stack = QStackedWidget()
        self._chat_stack.addWidget(self._empty_state)

        # Active chat widget
        self._active_chat = QWidget()
        active_layout = QVBoxLayout(self._active_chat)
        active_layout.setContentsMargins(0, 0, 0, 0)
        active_layout.setSpacing(0)

        # Chat header
        self._chat_header = QWidget()
        self._chat_header.setObjectName("chatHeader")
        header_layout = QHBoxLayout(self._chat_header)
        header_layout.setContentsMargins(16, 0, 16, 0)

        self._chat_header_name = QLabel("")
        self._chat_header_name.setObjectName("chatHeaderName")
        header_layout.addWidget(self._chat_header_name)

        self._chat_header_status = QLabel("")
        self._chat_header_status.setObjectName("chatHeaderStatus")
        header_layout.addWidget(self._chat_header_status)
        header_layout.addStretch()

        # Header buttons
        search_btn = self._header_button("🔍", "Поиск")
        pin_btn = self._header_button("📌", "Закреплённые")
        poll_btn = self._header_button("📊", "Создать опрос")
        poll_btn.clicked.connect(self._on_create_poll)

        header_layout.addWidget(search_btn)
        header_layout.addWidget(pin_btn)
        header_layout.addWidget(poll_btn)

        active_layout.addWidget(self._chat_header)

        # Chat view
        self._chat_view = ChatView(self._palette, self._accent)
        self._chat_view.load_more_requested.connect(self._on_load_more)
        self._chat_view.reply_requested.connect(self._on_reply)
        self._chat_view.edit_requested.connect(self._on_edit)
        self._chat_view.delete_requested.connect(self._on_delete_message)
        self._chat_view.reaction_requested.connect(self._on_reaction)
        self._chat_view.pin_requested.connect(self._on_pin)
        self._chat_view.forward_requested.connect(self._on_forward)
        self._chat_view.save_file_requested.connect(self._on_save_file)
        self._chat_view.message_visible.connect(self._on_message_visible)
        active_layout.addWidget(self._chat_view, 1)

        # Typing indicator
        self._typing_label = QLabel("")
        self._typing_label.setObjectName("typingIndicator")
        self._typing_label.setVisible(False)
        active_layout.addWidget(self._typing_label)

        # Message input
        self._message_input = MessageInput(self._palette, self._accent)
        self._message_input.message_submitted.connect(self._on_send_message)
        self._message_input.file_attach_requested.connect(self._on_attach_file)
        self._message_input.typing_started.connect(self._on_typing)
        self._message_input.emoji_picker_requested.connect(self._on_show_emoji_picker)
        self._message_input.edit_submitted.connect(self._on_edit_submit)
        active_layout.addWidget(self._message_input)

        self._chat_stack.addWidget(self._active_chat)
        chat_layout.addWidget(self._chat_stack, 1)

        # Connection bar
        self._connection_bar = ConnectionBar()
        chat_layout.addWidget(self._connection_bar)

        self._splitter.addWidget(chat_container)
        self._splitter.setSizes([300, 700])

        main_page_layout.addWidget(self._splitter)
        self._stack.addWidget(main_page)

    def _header_button(self, icon: str, tooltip: str) -> QPushButton:
        from PyQt5.QtWidgets import QPushButton
        btn = QPushButton(icon)
        btn.setObjectName("iconButton")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip(tooltip)
        btn.setFont(QFont("Segoe UI Emoji", 14))
        btn.setFixedSize(36, 36)
        return btn

    # ========================
    # System Tray
    # ========================

    def _setup_tray(self) -> None:
        self._tray = QSystemTrayIcon(self)
        self._tray.setToolTip("Lantern v2")

        # Создаём простую иконку
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)
        from PyQt5.QtGui import QPainter as P2
        p = P2(pixmap)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(self._accent.hex))
        p.drawEllipse(2, 2, 28, 28)
        p.end()
        self._tray.setIcon(QIcon(pixmap))

        tray_menu = QMenu()
        show_action = QAction("Показать", self)
        show_action.triggered.connect(self.show)
        tray_menu.addAction(show_action)

        quit_action = QAction("Выход", self)
        quit_action.triggered.connect(self._on_quit)
        tray_menu.addAction(quit_action)

        self._tray.setContextMenu(tray_menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.DoubleClick:
            self.show()
            self.activateWindow()

    # ========================
    # Theme
    # ========================

    def _apply_theme(self) -> None:
        qss = generate_stylesheet(self._palette.name, self._accent.name)
        QApplication.instance().setStyleSheet(qss)

    # ========================
    # WebSocket Callbacks
    # ========================

    def _setup_ws_callbacks(self) -> None:
        ws_client.set_callbacks(WSCallbacks(
            on_connected=self._ws_on_connected,
            on_disconnected=self._ws_on_disconnected,
            on_reconnecting=self._ws_on_reconnecting,
            on_reconnected=self._ws_on_reconnected,
            on_connection_failed=self._ws_on_connection_failed,
            on_new_message=self._ws_on_new_message,
            on_message_edited=self._ws_on_message_edited,
            on_message_deleted=self._ws_on_message_deleted,
            on_reaction_update=self._ws_on_reaction_update,
            on_typing=self._ws_on_typing,
            on_status_change=self._ws_on_status_change,
            on_poll_update=self._ws_on_poll_update,
            on_pin_update=self._ws_on_pin_update,
            on_error=self._ws_on_error,
        ))

    def _ws_on_connected(self): self._connection_bar.hide_bar()
    def _ws_on_disconnected(self): pass
    def _ws_on_reconnecting(self, attempt): self._connection_bar.show_reconnecting(attempt)
    def _ws_on_reconnected(self): self._connection_bar.hide_bar()
    def _ws_on_connection_failed(self, msg): self._connection_bar.show_error(msg)

    def _ws_on_new_message(self, data: dict):
        chat_id = data.get("chat_id")
        if chat_id == self._current_chat_id:
            self._chat_view.append_message(data)
        # Обновляем sidebar
        self._update_chat_in_sidebar(chat_id, data)
        # Уведомление
        author = data.get("author", {})
        if author.get("id") != (self._current_user or {}).get("id"):
            if chat_id != self._current_chat_id or not self.isActiveWindow():
                name = author.get("display_name", "")
                content = data.get("content", "Новое сообщение")
                send_system_notification(f"💬 {name}", content[:100])

    def _ws_on_message_edited(self, data: dict):
        if data.get("chat_id") == self._current_chat_id:
            self._chat_view.mark_edited(data["message_id"], data.get("new_content", ""))

    def _ws_on_message_deleted(self, data: dict):
        if data.get("chat_id") == self._current_chat_id:
            self._chat_view.delete_message(data["message_id"], data.get("for_everyone", False))

    def _ws_on_reaction_update(self, data: dict):
        if data.get("chat_id") == self._current_chat_id:
            self._chat_view.update_reactions(data["message_id"], data.get("reactions", []))

    def _ws_on_typing(self, data: dict):
        if data.get("chat_id") == self._current_chat_id:
            name = data.get("display_name", "")
            if data.get("is_typing"):
                self._typing_label.setText(f"  ✏️ {name} печатает...")
                self._typing_label.setVisible(True)
            else:
                self._typing_label.setVisible(False)

    def _ws_on_status_change(self, data: dict):
        user_id = data.get("user_id")
        status = data.get("status")
        if user_id and status:
            self._sidebar.update_user_status(user_id, status)

    def _ws_on_poll_update(self, data: dict):
        if data.get("chat_id") == self._current_chat_id:
            self._chat_view.update_poll(data.get("message_id", ""), data.get("poll", {}))

    def _ws_on_pin_update(self, data: dict):
        if data.get("chat_id") == self._current_chat_id:
            action = data.get("action")
            if action == "pin":
                msg = data.get("message", {})
                self._chat_view.mark_pinned(msg.get("id", ""), True)
            elif action == "unpin":
                self._chat_view.mark_pinned(data.get("message_id", ""), False)

    def _ws_on_error(self, data: dict):
        print(f"[WS Error] {data.get('message', '')}")

    # ========================
    # Auto Connect
    # ========================

    def _try_auto_connect(self) -> None:
        if self._config.server_host and self._config.auto_connect:
            host = self._config.server_host
            port = self._config.server_port
            self._login_widget.set_server_address(host, port)

            token = self._tokens.get_token(f"{host}:{port}")
            if token:
                asyncio.ensure_future(self._auto_login(host, port, token))

    async def _auto_login(self, host: str, port: int, token: str) -> None:
        await api_client.connect(host, port)
        api_client.set_token(token)
        result = await api_client.verify_token()
        if result.success:
            self._current_user = result.data
            await self._enter_main(host, port)
        else:
            self._tokens.remove_token(f"{host}:{port}")
            self._stack.setCurrentIndex(0)

    # ========================
    # Auth Handlers
    # ========================

    def _on_server_selected(self, host: str, port: int) -> None:
        asyncio.ensure_future(self._connect_server(host, port))

    def _on_manual_connect(self, host: str, port: int) -> None:
        asyncio.ensure_future(self._ping_server(host, port))

    async def _connect_server(self, host: str, port: int) -> None:
        await api_client.connect(host, port)

    async def _ping_server(self, host: str, port: int) -> None:
        await api_client.connect(host, port)
        result = await api_client.ping()
        self._login_widget.on_ping_result(result.success, result.error or "")

    def _on_login(self, username: str, password: str) -> None:
        asyncio.ensure_future(self._do_login(username, password))

    async def _do_login(self, username: str, password: str) -> None:
        host, port = self._login_widget.get_server_address()
        await api_client.connect(host, port)
        result = await api_client.login(username, password)
        if result.success:
            self._current_user = result.data.get("user")
            self._tokens.set_token(f"{host}:{port}", result.data.get("token", ""))
            await self._enter_main(host, port)
        else:
            self._login_widget.show_error(result.error or "Ошибка входа")

    def _on_register(self, username: str, password: str, display_name: str, nick_color: str) -> None:
        asyncio.ensure_future(self._do_register(username, password, display_name, nick_color))

    async def _do_register(self, username, password, display_name, nick_color) -> None:
        host, port = self._login_widget.get_server_address()
        await api_client.connect(host, port)
        result = await api_client.register(username, password, display_name, nick_color)
        if result.success:
            self._current_user = result.data.get("user")
            self._tokens.set_token(f"{host}:{port}", result.data.get("token", ""))
            await self._enter_main(host, port)
        else:
            self._login_widget.show_error(result.error or "Ошибка регистрации")

    async def _enter_main(self, host: str, port: int) -> None:
        self._config.server_host = host
        self._config.server_port = port
        self._config.last_username = self._current_user.get("username")
        self._config.save()

        self._login_widget.stop_discovery()

        # Устанавливаем пользователя
        user_id = self._current_user.get("id", "")
        self._chat_view.set_current_user(user_id)
        self._sidebar.set_current_user(self._current_user)

        # Загружаем данные
        chats_result = await api_client.get_chats()
        if chats_result.success:
            self._chats = chats_result.data
            self._sidebar.set_chats(self._chats)

        users_result = await api_client.get_all_users()
        if users_result.success:
            self._all_users = users_result.data

        # Подключаем WebSocket
        token = self._tokens.get_token(f"{host}:{port}")
        if token:
            await ws_client.connect(host, port, token)

        self._stack.setCurrentIndex(1)
        self._chat_stack.setCurrentIndex(0)  # Empty state

    # ========================
    # Chat Handlers
    # ========================

    def _on_chat_selected(self, chat_id: str) -> None:
        asyncio.ensure_future(self._load_chat(chat_id))

    async def _load_chat(self, chat_id: str) -> None:
        self._current_chat_id = chat_id
        self._chat_stack.setCurrentIndex(1)

        # Загружаем историю
        result = await api_client.get_messages(chat_id, limit=50)
        messages = result.data if result.success else []

        # Находим чат для заголовка
        chat_data = next((c for c in self._chats if c.get("id") == chat_id), {})
        self._chat_header_name.setText(chat_data.get("name", "Chat"))

        # Загружаем
        self._chat_view.load_chat(chat_id, messages)
        self._sidebar.set_selected_chat(chat_id)
        self._message_input.clear_input()
        self._message_input.set_focus()

        # Отмечаем прочитанным
        await api_client.mark_chat_read(chat_id)

    def _on_load_more(self) -> None:
        asyncio.ensure_future(self._do_load_more())

    async def _do_load_more(self) -> None:
        if not self._current_chat_id:
            return
        first_id = self._chat_view.get_first_message_id()
        result = await api_client.get_messages(self._current_chat_id, before=first_id, limit=50)
        if result.success:
            self._chat_view.prepend_messages(result.data)

    # ========================
    # Message Handlers
    # ========================

    def _on_send_message(self, content: str, reply_to_id: str) -> None:
        asyncio.ensure_future(self._do_send(content, reply_to_id))

    async def _do_send(self, content: str, reply_to_id: str) -> None:
        if not self._current_chat_id:
            return
        await ws_client.send_message(
            self._current_chat_id, content,
            reply_to_id if reply_to_id else None,
        )

    def _on_edit_submit(self, message_id: str, new_content: str) -> None:
        asyncio.ensure_future(ws_client.edit_message(message_id, new_content))

    def _on_reply(self, msg_data: dict) -> None:
        author = msg_data.get("author", {})
        self._message_input.set_reply(
            msg_data.get("id", ""),
            author.get("display_name", ""),
            author.get("nick_color", self._accent.hex),
            msg_data.get("content", ""),
            msg_data.get("message_type", "text"),
        )

    def _on_edit(self, msg_data: dict) -> None:
        self._message_input.set_edit(msg_data.get("id", ""), msg_data.get("content", ""))

    def _on_delete_message(self, message_id: str, for_everyone: bool) -> None:
        asyncio.ensure_future(ws_client.delete_message(message_id, for_everyone))

    def _on_reaction(self, message_id: str, emoji: str) -> None:
        asyncio.ensure_future(ws_client.toggle_reaction(message_id, emoji))

    def _on_pin(self, message_id: str, pin: bool) -> None:
        if pin:
            asyncio.ensure_future(ws_client.pin_message(message_id, self._current_chat_id))
        else:
            asyncio.ensure_future(ws_client.unpin_message(message_id, self._current_chat_id))

    def _on_forward(self, messages: list[dict]) -> None:
        dialog = ForwardDialog(
            self._chats, self._palette, self._accent,
            len(messages),
            self._current_user.get("id", "") if self._current_user else "",
            self,
        )
        dialog.chat_selected.connect(
            lambda cid: asyncio.ensure_future(
                ws_client.forward_messages([m.get("id", "") for m in messages], cid)
            )
        )
        dialog.exec_()

    def _on_typing(self) -> None:
        if self._current_chat_id:
            asyncio.ensure_future(ws_client.send_typing(self._current_chat_id))

    def _on_message_visible(self, message_id: str) -> None:
        if self._current_chat_id:
            asyncio.ensure_future(ws_client.mark_read(self._current_chat_id, message_id))

    # ========================
    # File Handlers
    # ========================

    def _on_attach_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Выберите файл")
        if path:
            asyncio.ensure_future(self._upload_file(path))

    async def _upload_file(self, path: str) -> None:
        if not self._current_chat_id:
            return
        reply_id = self._message_input._reply_message_id
        transfer = await file_transfer_manager.upload_file(
            self._current_chat_id, path, reply_id,
        )
        if transfer.state.value == "completed":
            self._message_input.cancel_reply()

    def _on_save_file(self, file_att: dict) -> None:
        save_dir = self._config.download_path
        asyncio.ensure_future(
            file_transfer_manager.download_file(
                file_att.get("id", ""),
                file_att.get("original_filename", "file"),
                file_att.get("file_size", 0),
                save_dir,
            )
        )

    # ========================
    # Other Handlers
    # ========================

    def _on_new_chat(self) -> None:
        dialog = NewChatDialog(
            self._all_users,
            self._current_user.get("id", "") if self._current_user else "",
            self._palette, self._accent, self,
        )
        dialog.user_selected.connect(self._on_create_direct_chat)
        dialog.exec_()

    def _on_create_direct_chat(self, user_id: str) -> None:
        asyncio.ensure_future(self._do_create_direct(user_id))

    async def _do_create_direct(self, user_id: str) -> None:
        result = await api_client.create_direct_chat(user_id)
        if result.success:
            chat_data = result.data
            self._sidebar.add_chat(chat_data)
            self._chats.append(chat_data)
            await self._load_chat(chat_data.get("id", ""))

    def _on_create_poll(self) -> None:
        dialog = PollDialog(self)
        dialog.poll_created.connect(self._on_poll_created)
        dialog.exec_()

    def _on_poll_created(self, question, options, anon, multi) -> None:
        if self._current_chat_id:
            asyncio.ensure_future(
                ws_client.create_poll(self._current_chat_id, question, options, anon, multi)
            )

    def _on_settings(self) -> None:
        dialog = SettingsDialog(
            self._palette, self._accent, self._current_user, self._config, self,
        )
        dialog.theme_changed.connect(self._on_theme_changed)
        dialog.profile_updated.connect(self._on_profile_updated)
        dialog.avatar_changed.connect(self._on_avatar_changed)
        dialog.download_path_changed.connect(self._on_download_path_changed)
        dialog.exec_()

    def _on_theme_changed(self, palette_name: str, accent_name: str) -> None:
        self._palette = get_palette(palette_name)
        self._accent = self._palette.get_accent(accent_name)
        self._config.theme.palette = palette_name
        self._config.theme.accent_color = accent_name
        self._config.save()
        self._apply_theme()
        self._chat_view.set_theme(self._palette, self._accent)
        self._sidebar.set_theme(self._palette, self._accent)
        self._message_input.set_theme(self._palette, self._accent)

    def _on_profile_updated(self, data: dict) -> None:
        asyncio.ensure_future(api_client.update_profile(**data))

    def _on_avatar_changed(self, path: str) -> None:
        asyncio.ensure_future(api_client.upload_avatar(path))

    def _on_download_path_changed(self, path: str) -> None:
        self._config.download_path = path
        self._config.save()

    def _on_status_change(self, status: str) -> None:
        asyncio.ensure_future(ws_client.set_status(status))

    def _on_show_emoji_picker(self, pos) -> None:
        if self._emoji_picker is None:
            self._emoji_picker = EmojiPicker()
            self._emoji_picker.emoji_selected.connect(self._message_input.insert_emoji)
        self._emoji_picker.show_at(pos)

    def _update_chat_in_sidebar(self, chat_id: str, new_message: dict) -> None:
        for chat in self._chats:
            if chat.get("id") == chat_id:
                chat["last_message"] = new_message
                if chat_id != self._current_chat_id:
                    chat["unread_count"] = chat.get("unread_count", 0) + 1
                self._sidebar.update_chat(chat)
                return
        # Новый чат — перезагружаем список
        asyncio.ensure_future(self._reload_chats())

    async def _reload_chats(self) -> None:
        result = await api_client.get_chats()
        if result.success:
            self._chats = result.data
            self._sidebar.set_chats(self._chats)

    # ========================
    # Window Events
    # ========================

    def closeEvent(self, event: QCloseEvent) -> None:
        # Сохраняем геометрию
        settings = QSettings("Lantern", "v2")
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("windowState", self.saveState())

        # Сворачиваем в трей
        if self._tray.isVisible():
            self.hide()
            event.ignore()
        else:
            self._on_quit()

    def _on_quit(self) -> None:
        asyncio.ensure_future(self._cleanup())
        QApplication.instance().quit()

    async def _cleanup(self) -> None:
        await ws_client.disconnect()
        await api_client.close()


def run_client():
    """Запуск клиента."""
    app = QApplication(sys.argv)
    app.setApplicationName("Lantern v2")
    app.setOrganizationName("Lantern")

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    window = MainWindow()
    window.show()

    with loop:
        loop.run_forever()


if __name__ == "__main__":
    run_client()