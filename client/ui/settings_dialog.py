"""
Lantern v2 — Settings Dialog
Полноценные настройки: профиль, тема, чат, уведомления, файлы, подключение.
"""

from typing import Optional
from pathlib import Path

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget,
    QWidget, QLabel, QPushButton, QLineEdit, QComboBox,
    QCheckBox, QSlider, QFileDialog, QGridLayout,
    QFrame, QScrollArea, QSizePolicy, QSpinBox
)
from PyQt5.QtGui import QFont, QColor, QPixmap
from PyQt5.QtCore import Qt, pyqtSignal, QSize

from client.ui.components.avatar import AvatarWidget
from client.themes.catppuccin import (
    Palette, AccentColor, PALETTES, get_palette
)


class SettingsDialog(QDialog):
    """
    Диалог настроек.

    Сигналы:
        theme_changed(str, str): palette_name, accent_name
        profile_updated(dict): {display_name, nick_color, custom_status_text}
        avatar_changed(str): file_path
        download_path_changed(str): new_path
        notification_settings_changed(dict)
        chat_settings_changed(dict)
    """

    theme_changed = pyqtSignal(str, str)
    profile_updated = pyqtSignal(dict)
    avatar_changed = pyqtSignal(str)
    download_path_changed = pyqtSignal(str)
    notification_settings_changed = pyqtSignal(dict)
    chat_settings_changed = pyqtSignal(dict)

    ACCENT_NAMES = [
        "rosewater", "flamingo", "pink", "mauve",
        "red", "maroon", "peach", "yellow",
        "green", "teal", "sky", "sapphire",
        "blue", "lavender",
    ]

    def __init__(
        self,
        palette: Palette,
        accent: AccentColor,
        current_user: Optional[dict] = None,
        config: Optional[object] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("⚙️ Настройки")
        self.setMinimumSize(600, 520)
        self.setModal(True)

        self._palette = palette
        self._accent = accent
        self._current_user = current_user or {}
        self._config = config
        self._pending_changes: dict = {}

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        tabs = QTabWidget()
        tabs.addTab(self._create_profile_tab(), "👤 Профиль")
        tabs.addTab(self._create_appearance_tab(), "🎨 Внешний вид")
        tabs.addTab(self._create_chat_tab(), "💬 Чат")
        tabs.addTab(self._create_notifications_tab(), "🔔 Уведомления")
        tabs.addTab(self._create_files_tab(), "📁 Файлы")

        layout.addWidget(tabs)

        # Кнопки
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(16, 12, 16, 12)
        btn_row.addStretch()

        cancel_btn = QPushButton("Отмена")
        cancel_btn.setObjectName("secondaryButton")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("💾 Сохранить")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)

    # ========================
    # Profile Tab
    # ========================

    def _create_profile_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        page = QWidget()
        page.setObjectName("settingsPage")
        layout = QVBoxLayout(page)
        layout.setSpacing(16)

        # Аватар
        layout.addWidget(self._section_title("АВАТАР"))

        avatar_row = QHBoxLayout()
        avatar_row.setSpacing(16)

        self._avatar_widget = AvatarWidget(size="large", show_status=False)
        display_name = self._current_user.get("display_name", "?")
        nick_color = self._current_user.get("nick_color", self._accent.hex)
        self._avatar_widget.set_initials(display_name, nick_color)
        avatar_row.addWidget(self._avatar_widget)

        avatar_btns = QVBoxLayout()
        avatar_btns.setSpacing(8)

        upload_btn = QPushButton("📷 Загрузить фото")
        upload_btn.setObjectName("secondaryButton")
        upload_btn.setCursor(Qt.PointingHandCursor)
        upload_btn.clicked.connect(self._on_upload_avatar)
        avatar_btns.addWidget(upload_btn)

        remove_btn = QPushButton("🗑️ Удалить")
        remove_btn.setObjectName("ghostButton")
        remove_btn.setCursor(Qt.PointingHandCursor)
        avatar_btns.addWidget(remove_btn)

        avatar_btns.addStretch()
        avatar_row.addLayout(avatar_btns)
        avatar_row.addStretch()
        layout.addLayout(avatar_row)

        # Отображаемый ник
        layout.addWidget(self._section_title("ПРОФИЛЬ"))

        nick_item = self._setting_item("Отображаемый ник")
        self._display_name_input = QLineEdit(self._current_user.get("display_name", ""))
        self._display_name_input.setMaxLength(128)
        self._display_name_input.setPlaceholderText("Ваш ник")
        nick_item.layout().addWidget(self._display_name_input)
        layout.addWidget(nick_item)

        # Цвет ника
        layout.addWidget(self._section_title("ЦВЕТ НИКА"))

        color_grid = QGridLayout()
        color_grid.setSpacing(8)
        self._nick_color_buttons: list[QPushButton] = []
        current_nick_color = self._current_user.get("nick_color", "#cba6f7")

        for i, name in enumerate(self.ACCENT_NAMES):
            color_hex = getattr(self._palette, name)
            btn = QPushButton()
            btn.setFixedSize(36, 36)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(name)
            is_selected = color_hex.lower() == current_nick_color.lower()
            self._style_color_btn(btn, color_hex, is_selected)
            btn.clicked.connect(lambda c, h=color_hex, b=btn: self._on_nick_color_selected(h, b))
            self._nick_color_buttons.append(btn)
            color_grid.addWidget(btn, i // 7, i % 7)

        layout.addLayout(color_grid)

        # Пользовательский статус
        status_item = self._setting_item("Пользовательский статус")
        self._custom_status_input = QLineEdit(
            self._current_user.get("custom_status_text", "") or ""
        )
        self._custom_status_input.setMaxLength(128)
        self._custom_status_input.setPlaceholderText("Что у вас нового?")
        status_item.layout().addWidget(self._custom_status_input)
        layout.addWidget(status_item)

        layout.addStretch()
        scroll.setWidget(page)
        return scroll

    # ========================
    # Appearance Tab
    # ========================

    def _create_appearance_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        page = QWidget()
        page.setObjectName("settingsPage")
        layout = QVBoxLayout(page)
        layout.setSpacing(16)

        # Палитра
        layout.addWidget(self._section_title("ТЕМА"))

        self._palette_combo = QComboBox()
        for name, pal in PALETTES.items():
            self._palette_combo.addItem(pal.display_name, name)
        current_idx = list(PALETTES.keys()).index(self._palette.name) if self._palette.name in PALETTES else 3
        self._palette_combo.setCurrentIndex(current_idx)
        self._palette_combo.currentIndexChanged.connect(self._on_palette_changed)
        layout.addWidget(self._palette_combo)

        # Превью палитры
        self._palette_preview = QLabel()
        self._palette_preview.setFixedHeight(40)
        self._update_palette_preview()
        layout.addWidget(self._palette_preview)

        # Акцентный цвет
        layout.addWidget(self._section_title("АКЦЕНТНЫЙ ЦВЕТ"))

        accent_grid = QGridLayout()
        accent_grid.setSpacing(8)
        self._accent_buttons: list[QPushButton] = []

        for i, name in enumerate(self.ACCENT_NAMES):
            color_hex = getattr(self._palette, name)
            btn = QPushButton()
            btn.setFixedSize(36, 36)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(name)
            is_selected = name == self._accent.name
            self._style_color_btn(btn, color_hex, is_selected)
            btn.clicked.connect(lambda c, n=name, b=btn: self._on_accent_selected(n, b))
            self._accent_buttons.append(btn)
            accent_grid.addWidget(btn, i // 7, i % 7)

        layout.addLayout(accent_grid)

        layout.addStretch()
        scroll.setWidget(page)
        return scroll

    # ========================
    # Chat Tab
    # ========================

    def _create_chat_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        page = QWidget()
        page.setObjectName("settingsPage")
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        layout.addWidget(self._section_title("ВВОД СООБЩЕНИЙ"))

        self._enter_sends_check = QCheckBox("Enter отправляет сообщение")
        self._enter_sends_check.setChecked(True)
        layout.addWidget(self._enter_sends_check)

        hint = QLabel("Если включено: Enter = отправить, Shift+Enter = новая строка")
        hint.setObjectName("mutedLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        layout.addWidget(self._section_title("РАЗМЕР ШРИФТА"))

        font_row = QHBoxLayout()
        self._font_size_spin = QSpinBox()
        self._font_size_spin.setRange(10, 24)
        self._font_size_spin.setValue(14)
        self._font_size_spin.setSuffix(" px")
        font_row.addWidget(self._font_size_spin)
        font_row.addStretch()
        layout.addLayout(font_row)

        layout.addWidget(self._section_title("ОТОБРАЖЕНИЕ"))

        self._show_timestamps_check = QCheckBox("Показывать время сообщений")
        self._show_timestamps_check.setChecked(True)
        layout.addWidget(self._show_timestamps_check)

        self._typing_indicator_check = QCheckBox("Показывать индикатор «печатает...»")
        self._typing_indicator_check.setChecked(True)
        layout.addWidget(self._typing_indicator_check)

        layout.addStretch()
        scroll.setWidget(page)
        return scroll

    # ========================
    # Notifications Tab
    # ========================

    def _create_notifications_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        page = QWidget()
        page.setObjectName("settingsPage")
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        layout.addWidget(self._section_title("УВЕДОМЛЕНИЯ"))

        self._notif_enabled_check = QCheckBox("Включить уведомления")
        self._notif_enabled_check.setChecked(True)
        layout.addWidget(self._notif_enabled_check)

        self._notif_sound_check = QCheckBox("Звук уведомлений")
        self._notif_sound_check.setChecked(True)
        layout.addWidget(self._notif_sound_check)

        self._notif_preview_check = QCheckBox("Показывать текст сообщения в уведомлении")
        self._notif_preview_check.setChecked(True)
        layout.addWidget(self._notif_preview_check)

        layout.addStretch()
        scroll.setWidget(page)
        return scroll

    # ========================
    # Files Tab
    # ========================

    def _create_files_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        page = QWidget()
        page.setObjectName("settingsPage")
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        layout.addWidget(self._section_title("ПУТЬ СОХРАНЕНИЯ ФАЙЛОВ"))

        path_row = QHBoxLayout()
        self._download_path_input = QLineEdit(
            str(Path.home() / "Downloads" / "Lantern")
        )
        path_row.addWidget(self._download_path_input, 1)

        browse_btn = QPushButton("📂 Обзор")
        browse_btn.setObjectName("secondaryButton")
        browse_btn.setCursor(Qt.PointingHandCursor)
        browse_btn.clicked.connect(self._on_browse_path)
        path_row.addWidget(browse_btn)

        layout.addLayout(path_row)

        layout.addStretch()
        scroll.setWidget(page)
        return scroll

    # ========================
    # Helpers
    # ========================

    def _section_title(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("settingsSectionTitle")
        return label

    def _setting_item(self, label_text: str) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        label = QLabel(label_text)
        label.setObjectName("mutedLabel")
        layout.addWidget(label)
        return widget

    def _style_color_btn(self, btn: QPushButton, color: str, selected: bool) -> None:
        border = f"3px solid {self._palette.text}" if selected else "2px solid transparent"
        btn.setStyleSheet(
            f"QPushButton {{ background-color: {color}; border-radius: 18px; border: {border}; }}"
            f"QPushButton:hover {{ border: 2px solid {self._palette.text}; }}"
        )

    # ========================
    # Event Handlers
    # ========================

    def _on_palette_changed(self, index: int) -> None:
        name = self._palette_combo.itemData(index)
        if name:
            self._pending_changes["palette"] = name
            self._update_palette_preview()

    def _update_palette_preview(self) -> None:
        pal_name = self._pending_changes.get("palette", self._palette.name)
        pal = get_palette(pal_name)
        colors = [pal.base, pal.surface0, pal.surface1, pal.text, pal.mauve, pal.blue, pal.green, pal.red]
        gradient = " ".join(
            f'<span style="color:{c}; font-size:24px;">■</span>' for c in colors
        )
        self._palette_preview.setText(gradient)
        self._palette_preview.setTextFormat(Qt.RichText)

    def _on_accent_selected(self, name: str, button: QPushButton) -> None:
        self._pending_changes["accent"] = name
        for btn in self._accent_buttons:
            self._style_color_btn(btn, btn.toolTip(), False)
        pal_name = self._pending_changes.get("palette", self._palette.name)
        pal = get_palette(pal_name)
        color_hex = getattr(pal, name)
        self._style_color_btn(button, color_hex, True)

    def _on_nick_color_selected(self, color_hex: str, button: QPushButton) -> None:
        self._pending_changes["nick_color"] = color_hex
        for btn in self._nick_color_buttons:
            self._style_color_btn(btn, btn.styleSheet().split("background-color:")[1].split(";")[0].strip() if "background-color:" in btn.styleSheet() else "#cba6f7", False)
        self._style_color_btn(button, color_hex, True)

    def _on_upload_avatar(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите аватар", "",
            "Images (*.png *.jpg *.jpeg *.webp *.gif)"
        )
        if path:
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                self._avatar_widget.set_image(pixmap)
                self._pending_changes["avatar_path"] = path

    def _on_browse_path(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Выберите папку")
        if path:
            self._download_path_input.setText(path)

    def _on_save(self) -> None:
        # Тема
        pal_name = self._pending_changes.get("palette")
        acc_name = self._pending_changes.get("accent")
        if pal_name or acc_name:
            self.theme_changed.emit(
                pal_name or self._palette.name,
                acc_name or self._accent.name,
            )

        # Профиль
        profile = {}
        new_name = self._display_name_input.text().strip()
        if new_name and new_name != self._current_user.get("display_name"):
            profile["display_name"] = new_name
        nick_color = self._pending_changes.get("nick_color")
        if nick_color:
            profile["nick_color"] = nick_color
        status_text = self._custom_status_input.text().strip()
        if status_text != (self._current_user.get("custom_status_text") or ""):
            profile["custom_status_text"] = status_text
        if profile:
            self.profile_updated.emit(profile)

        # Аватар
        avatar_path = self._pending_changes.get("avatar_path")
        if avatar_path:
            self.avatar_changed.emit(avatar_path)

        # Файлы
        dl_path = self._download_path_input.text().strip()
        if dl_path:
            self.download_path_changed.emit(dl_path)

        # Чат
        self.chat_settings_changed.emit({
            "enter_sends": self._enter_sends_check.isChecked(),
            "font_size": self._font_size_spin.value(),
            "show_timestamps": self._show_timestamps_check.isChecked(),
            "show_typing": self._typing_indicator_check.isChecked(),
        })

        # Уведомления
        self.notification_settings_changed.emit({
            "enabled": self._notif_enabled_check.isChecked(),
            "sound": self._notif_sound_check.isChecked(),
            "preview": self._notif_preview_check.isChecked(),
        })

        self.accept()