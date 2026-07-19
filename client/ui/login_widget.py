"""
Lantern v2 — Login & Registration Widget
Красивый экран входа/регистрации в стиле Catppuccin.

Два режима:
1. Login — логин + пароль
2. Register — логин + пароль + отображаемый ник + цвет ника

Автоматический переход между режимами.
Глазик показать/скрыть пароль.
После регистрации — автоматический вход.
"""

from typing import Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QLabel, QFrame, QSizePolicy,
    QGraphicsOpacityEffect, QStackedWidget, QApplication,
    QGridLayout, QScrollArea
)
from PyQt5.QtGui import QFont, QColor, QPainter, QPainterPath, QCursor
from PyQt5.QtCore import (
    Qt, pyqtSignal, QSize, QPropertyAnimation,
    QEasingCurve, QTimer, QPoint
)

from client.themes.catppuccin import get_palette, Palette, AccentColor, PALETTES
from client.network.discovery import ServerDiscovery, DiscoveredServer


class LoginWidget(QWidget):
    """
    Экран входа / регистрации.

    Сигналы:
        login_requested: (username, password)
        register_requested: (username, password, display_name, nick_color)
        server_selected: (host, port)
        manual_connect_requested: (host, port)
    """

    login_requested = pyqtSignal(str, str)
    register_requested = pyqtSignal(str, str, str, str)
    server_selected = pyqtSignal(str, int)
    manual_connect_requested = pyqtSignal(str, int)

    # Цвета ников для выбора (Catppuccin Mocha accents)
    NICK_COLORS = [
        ("#f5e0dc", "Rosewater"), ("#f2cdcd", "Flamingo"),
        ("#f5c2e7", "Pink"), ("#cba6f7", "Mauve"),
        ("#f38ba8", "Red"), ("#eba0ac", "Maroon"),
        ("#fab387", "Peach"), ("#f9e2af", "Yellow"),
        ("#a6e3a1", "Green"), ("#94e2d5", "Teal"),
        ("#89dceb", "Sky"), ("#74c7ec", "Sapphire"),
        ("#89b4fa", "Blue"), ("#b4befe", "Lavender"),
    ]

    def __init__(
        self,
        palette: Palette,
        accent: AccentColor,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setObjectName("loginPage")
        self._palette = palette
        self._accent = accent
        self._is_register_mode = False
        self._selected_nick_color = "#cba6f7"
        self._discovery = ServerDiscovery()
        self._discovered_servers: list[DiscoveredServer] = []

        self._setup_ui()
        self._start_discovery()

    def _setup_ui(self) -> None:
        """Строит UI."""
        # Фон
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        # Центрирующий контейнер
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setAlignment(Qt.AlignCenter)

        # === Карточка ===
        self._card = QWidget()
        self._card.setObjectName("loginCard")
        self._card.setFixedWidth(420)

        card_layout = QVBoxLayout(self._card)
        card_layout.setSpacing(16)
        card_layout.setContentsMargins(40, 40, 40, 40)

        # Лого
        logo_label = QLabel("🏮")
        logo_label.setObjectName("loginLogo")
        logo_label.setAlignment(Qt.AlignCenter)
        logo_label.setFont(QFont("Segoe UI Emoji", 48))
        card_layout.addWidget(logo_label)

        # Заголовок
        self._title_label = QLabel("Lantern v2")
        self._title_label.setObjectName("loginTitle")
        self._title_label.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(self._title_label)

        # Подзаголовок
        self._subtitle_label = QLabel("Войдите в аккаунт")
        self._subtitle_label.setObjectName("loginSubtitle")
        self._subtitle_label.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(self._subtitle_label)

        # === Сервер ===
        server_label = QLabel("Сервер")
        server_label.setObjectName("mutedLabel")
        card_layout.addWidget(server_label)

        server_row = QHBoxLayout()
        server_row.setSpacing(8)

        self._server_input = QLineEdit()
        self._server_input.setPlaceholderText("IP:порт или выберите ниже...")
        server_row.addWidget(self._server_input, 1)

        self._ping_btn = QPushButton("Проверить")
        self._ping_btn.setObjectName("secondaryButton")
        self._ping_btn.setCursor(Qt.PointingHandCursor)
        self._ping_btn.clicked.connect(self._on_ping)
        server_row.addWidget(self._ping_btn)

        card_layout.addLayout(server_row)

        # Обнаруженные серверы
        self._servers_container = QWidget()
        self._servers_layout = QVBoxLayout(self._servers_container)
        self._servers_layout.setContentsMargins(0, 0, 0, 0)
        self._servers_layout.setSpacing(4)
        card_layout.addWidget(self._servers_container)

        self._server_status_label = QLabel("🔍 Поиск серверов в сети...")
        self._server_status_label.setObjectName("mutedLabel")
        self._servers_layout.addWidget(self._server_status_label)

        # Разделитель
        sep = QFrame()
        sep.setObjectName("separator")
        sep.setFrameShape(QFrame.HLine)
        card_layout.addWidget(sep)

        # === Поля ввода ===
        # Логин
        username_label = QLabel("Логин")
        username_label.setObjectName("mutedLabel")
        card_layout.addWidget(username_label)

        self._username_input = QLineEdit()
        self._username_input.setPlaceholderText("username")
        self._username_input.setMaxLength(64)
        card_layout.addWidget(self._username_input)

        # Пароль
        password_label = QLabel("Пароль")
        password_label.setObjectName("mutedLabel")
        card_layout.addWidget(password_label)

        password_row = QHBoxLayout()
        password_row.setSpacing(0)

        self._password_input = QLineEdit()
        self._password_input.setPlaceholderText("••••••••")
        self._password_input.setEchoMode(QLineEdit.Password)
        self._password_input.setMaxLength(128)
        password_row.addWidget(self._password_input, 1)

        self._show_pass_btn = QPushButton("👁")
        self._show_pass_btn.setObjectName("showPasswordButton")
        self._show_pass_btn.setCursor(Qt.PointingHandCursor)
        self._show_pass_btn.setCheckable(True)
        self._show_pass_btn.toggled.connect(self._toggle_password_visibility)
        self._show_pass_btn.setFixedSize(36, 36)
        password_row.addWidget(self._show_pass_btn)

        card_layout.addLayout(password_row)

        # === Поля регистрации (скрыты по умолчанию) ===
        self._register_fields = QWidget()
        self._register_fields.setVisible(False)
        reg_layout = QVBoxLayout(self._register_fields)
        reg_layout.setContentsMargins(0, 0, 0, 0)
        reg_layout.setSpacing(12)

        # Отображаемый ник
        nick_label = QLabel("Отображаемый ник")
        nick_label.setObjectName("mutedLabel")
        reg_layout.addWidget(nick_label)

        self._display_name_input = QLineEdit()
        self._display_name_input.setPlaceholderText("Как вас будут видеть другие")
        self._display_name_input.setMaxLength(128)
        reg_layout.addWidget(self._display_name_input)

        # Цвет ника
        color_label = QLabel("Цвет ника")
        color_label.setObjectName("mutedLabel")
        reg_layout.addWidget(color_label)

        color_grid = QGridLayout()
        color_grid.setSpacing(8)
        self._color_buttons: list[QPushButton] = []

        for i, (color_hex, color_name) in enumerate(self.NICK_COLORS):
            btn = QPushButton()
            btn.setFixedSize(32, 32)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(color_name)
            btn.setStyleSheet(
                f"QPushButton {{ background-color: {color_hex}; "
                f"border-radius: 16px; border: 2px solid transparent; }}"
                f"QPushButton:hover {{ border-color: {self._palette.text}; }}"
            )
            btn.clicked.connect(lambda checked, c=color_hex, b=btn: self._select_nick_color(c, b))
            self._color_buttons.append(btn)

            row = i // 7
            col = i % 7
            color_grid.addWidget(btn, row, col)

        reg_layout.addLayout(color_grid)

        # Выбираем mauve по умолчанию
        self._select_nick_color("#cba6f7", self._color_buttons[3])

        card_layout.addWidget(self._register_fields)

        # === Ошибка ===
        self._error_label = QLabel("")
        self._error_label.setObjectName("errorLabel")
        self._error_label.setAlignment(Qt.AlignCenter)
        self._error_label.setWordWrap(True)
        self._error_label.setVisible(False)
        card_layout.addWidget(self._error_label)

        # === Кнопка входа/регистрации ===
        self._submit_btn = QPushButton("Войти")
        self._submit_btn.setCursor(Qt.PointingHandCursor)
        self._submit_btn.setFont(QFont("Segoe UI", 14, QFont.DemiBold))
        self._submit_btn.setMinimumHeight(44)
        self._submit_btn.clicked.connect(self._on_submit)
        card_layout.addWidget(self._submit_btn)

        # === Переключатель режима ===
        switch_row = QHBoxLayout()
        switch_row.setAlignment(Qt.AlignCenter)

        self._switch_label = QLabel("Нет аккаунта?")
        self._switch_label.setObjectName("mutedLabel")
        switch_row.addWidget(self._switch_label)

        self._switch_btn = QPushButton("Создать")
        self._switch_btn.setObjectName("ghostButton")
        self._switch_btn.setCursor(Qt.PointingHandCursor)
        self._switch_btn.clicked.connect(self._toggle_mode)
        switch_row.addWidget(self._switch_btn)

        card_layout.addLayout(switch_row)

        # === Копирайт ===
        credit = QLabel("Made by dimasbotyara")
        credit.setObjectName("mutedLabel")
        credit.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(credit)

        center_layout.addWidget(self._card)
        outer_layout.addWidget(center_widget)

        # Enter для отправки
        self._password_input.returnPressed.connect(self._on_submit)
        self._username_input.returnPressed.connect(
            lambda: self._password_input.setFocus()
        )

    # ========================
    # Server Discovery
    # ========================

    def _start_discovery(self) -> None:
        """Запускает поиск серверов."""
        try:
            self._discovery.start(on_update=self._on_servers_updated)
        except Exception:
            self._server_status_label.setText("⚠️ Zeroconf недоступен")

    def _on_servers_updated(self, servers: list[DiscoveredServer]) -> None:
        """Обновляет список найденных серверов."""
        self._discovered_servers = servers

        # Очищаем старые кнопки
        while self._servers_layout.count() > 0:
            item = self._servers_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not servers:
            label = QLabel("🔍 Поиск серверов в сети...")
            label.setObjectName("mutedLabel")
            self._servers_layout.addWidget(label)
            return

        for server in servers:
            btn = QPushButton(f"🏮 {server.name} ({server.host}:{server.port})")
            btn.setObjectName("secondaryButton")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(
                lambda checked, s=server: self._on_server_selected(s)
            )
            self._servers_layout.addWidget(btn)

    def _on_server_selected(self, server: DiscoveredServer) -> None:
        """Выбор сервера из списка."""
        self._server_input.setText(f"{server.host}:{server.port}")
        self.server_selected.emit(server.host, server.port)

    def _on_ping(self) -> None:
        """Проверка соединения с сервером."""
        address = self._server_input.text().strip()
        if not address:
            self.show_error("Введите адрес сервера")
            return

        host, port = self._parse_address(address)
        if host:
            self._ping_btn.setText("⏳")
            self._ping_btn.setEnabled(False)
            self.manual_connect_requested.emit(host, port)

    def on_ping_result(self, success: bool, info: str = "") -> None:
        """Результат пинга сервера."""
        self._ping_btn.setEnabled(True)
        if success:
            self._ping_btn.setText("✅")
            QTimer.singleShot(2000, lambda: self._ping_btn.setText("Проверить"))
        else:
            self._ping_btn.setText("❌")
            self.show_error(info or "Сервер недоступен")
            QTimer.singleShot(2000, lambda: self._ping_btn.setText("Проверить"))

    # ========================
    # Mode Switching
    # ========================

    def _toggle_mode(self) -> None:
        """Переключает между логином и регистрацией."""
        self._is_register_mode = not self._is_register_mode
        self._error_label.setVisible(False)

        if self._is_register_mode:
            self._title_label.setText("Lantern v2")
            self._subtitle_label.setText("Создайте аккаунт")
            self._submit_btn.setText("Зарегистрироваться")
            self._switch_label.setText("Уже есть аккаунт?")
            self._switch_btn.setText("Войти")
            self._register_fields.setVisible(True)
        else:
            self._title_label.setText("Lantern v2")
            self._subtitle_label.setText("Войдите в аккаунт")
            self._submit_btn.setText("Войти")
            self._switch_label.setText("Нет аккаунта?")
            self._switch_btn.setText("Создать")
            self._register_fields.setVisible(False)

    # ========================
    # Nick Color
    # ========================

    def _select_nick_color(self, color: str, button: QPushButton) -> None:
        """Выбирает цвет ника."""
        self._selected_nick_color = color

        # Сбрасываем стили всех кнопок
        for btn in self._color_buttons:
            hex_color = btn.toolTip()
            actual_color = ""
            for c, n in self.NICK_COLORS:
                if n == hex_color:
                    actual_color = c
                    break
            if not actual_color:
                # Fallback
                actual_color = btn.styleSheet().split("background-color:")[1].split(";")[0].strip() if "background-color:" in btn.styleSheet() else "#cba6f7"

            btn.setStyleSheet(
                f"QPushButton {{ background-color: {actual_color}; "
                f"border-radius: 16px; border: 2px solid transparent; }}"
                f"QPushButton:hover {{ border-color: {self._palette.text}; }}"
            )

        # Подсвечиваем выбранную
        button.setStyleSheet(
            f"QPushButton {{ background-color: {color}; "
            f"border-radius: 16px; border: 3px solid {self._palette.text}; }}"
        )

    # ========================
    # Submit
    # ========================

    def _on_submit(self) -> None:
        """Обработка нажатия кнопки."""
        self._error_label.setVisible(False)

        # Проверяем сервер
        address = self._server_input.text().strip()
        if not address:
            self.show_error("Укажите адрес сервера")
            return

        username = self._username_input.text().strip()
        password = self._password_input.text()

        if not username:
            self.show_error("Введите логин")
            return

        if len(username) < 3:
            self.show_error("Логин должен быть не менее 3 символов")
            return

        if not password:
            self.show_error("Введите пароль")
            return

        if len(password) < 4:
            self.show_error("Пароль должен быть не менее 4 символов")
            return

        if self._is_register_mode:
            display_name = self._display_name_input.text().strip()
            if not display_name:
                self.show_error("Введите отображаемый ник")
                return

            self._submit_btn.setText("⏳ Регистрация...")
            self._submit_btn.setEnabled(False)
            self.register_requested.emit(
                username, password, display_name, self._selected_nick_color
            )
        else:
            self._submit_btn.setText("⏳ Вход...")
            self._submit_btn.setEnabled(False)
            self.login_requested.emit(username, password)

    def show_error(self, message: str) -> None:
        """Показывает ошибку."""
        self._error_label.setText(message)
        self._error_label.setVisible(True)

        # Сбрасываем кнопку
        if self._is_register_mode:
            self._submit_btn.setText("Зарегистрироваться")
        else:
            self._submit_btn.setText("Войти")
        self._submit_btn.setEnabled(True)

    def reset(self) -> None:
        """Сбрасывает форму."""
        if self._is_register_mode:
            self._submit_btn.setText("Зарегистрироваться")
        else:
            self._submit_btn.setText("Войти")
        self._submit_btn.setEnabled(True)
        self._error_label.setVisible(False)

    def set_server_address(self, host: str, port: int) -> None:
        """Устанавливает адрес сервера."""
        self._server_input.setText(f"{host}:{port}")

    def get_server_address(self) -> tuple[str, int]:
        """Возвращает введённый адрес сервера."""
        address = self._server_input.text().strip()
        return self._parse_address(address)

    def _parse_address(self, address: str) -> tuple[str, int]:
        """Парсит адрес 'host:port'."""
        try:
            if ":" in address:
                parts = address.rsplit(":", 1)
                return parts[0], int(parts[1])
            else:
                return address, 8190
        except (ValueError, IndexError):
            return address, 8190

    def _toggle_password_visibility(self, show: bool) -> None:
        """Переключает видимость пароля."""
        if show:
            self._password_input.setEchoMode(QLineEdit.Normal)
            self._show_pass_btn.setText("🙈")
        else:
            self._password_input.setEchoMode(QLineEdit.Password)
            self._show_pass_btn.setText("👁")

    def stop_discovery(self) -> None:
        """Останавливает поиск серверов."""
        self._discovery.stop()