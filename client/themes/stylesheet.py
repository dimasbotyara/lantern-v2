"""
Lantern v2 — QSS Stylesheet Generator
Генерирует полный Qt StyleSheet из палитры Catppuccin + акцентного цвета.
Каждый виджет стилизуется отдельно для pixel-perfect результата.
"""

from client.themes.catppuccin import Palette, AccentColor, get_palette


class StyleSheetGenerator:
    """
    Генератор QSS-стилей для всего приложения.

    Принимает палитру и акцентный цвет, возвращает полный QSS.
    Все размеры, отступы, скругления и цвета — в одном месте.
    """

    def __init__(self, palette: Palette, accent: AccentColor):
        self.p = palette
        self.a = accent

    def generate(self) -> str:
        """Генерирует полный QSS для приложения."""
        sections = [
            self._global_styles(),
            self._scrollbar_styles(),
            self._button_styles(),
            self._input_styles(),
            self._label_styles(),
            self._sidebar_styles(),
            self._chat_header_styles(),
            self._message_input_styles(),
            self._context_menu_styles(),
            self._dialog_styles(),
            self._tab_widget_styles(),
            self._tooltip_styles(),
            self._checkbox_radio_styles(),
            self._slider_styles(),
            self._progress_bar_styles(),
            self._notification_styles(),
            self._connection_bar_styles(),
            self._search_styles(),
            self._pinned_bar_styles(),
            self._emoji_picker_styles(),
            self._sticker_picker_styles(),
            self._poll_styles(),
            self._reply_preview_styles(),
            self._settings_styles(),
            self._login_styles(),
            self._avatar_styles(),
            self._badge_styles(),
            self._file_preview_styles(),
            self._date_separator_styles(),
            self._typing_indicator_styles(),
            self._splitter_styles(),
            self._combo_box_styles(),
        ]
        return "\n\n".join(sections)

    # ========================
    # Global
    # ========================

    def _global_styles(self) -> str:
        return f"""
/* ===== GLOBAL ===== */
QWidget {{
    background-color: {self.p.base};
    color: {self.p.text};
    font-family: "Segoe UI", "SF Pro Display", "Helvetica Neue", "Noto Sans", "Noto Color Emoji", sans-serif;
    font-size: 14px;
    selection-background-color: {self.a.hex};
    selection-color: {self.p.crust};
}}

QMainWindow {{
    background-color: {self.p.base};
}}

QFrame {{
    border: none;
}}

QFrame#separator {{
    background-color: {self.p.surface0};
    max-height: 1px;
    min-height: 1px;
}}
"""

    # ========================
    # Scrollbar
    # ========================

    def _scrollbar_styles(self) -> str:
        return f"""
/* ===== SCROLLBAR ===== */
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 0;
    border: none;
}}

QScrollBar::handle:vertical {{
    background: {self.p.surface1};
    min-height: 40px;
    border-radius: 4px;
    margin: 2px;
}}

QScrollBar::handle:vertical:hover {{
    background: {self.p.surface2};
}}

QScrollBar::handle:vertical:pressed {{
    background: {self.p.overlay0};
}}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {{
    height: 0;
    background: transparent;
    border: none;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 0;
    border: none;
}}

QScrollBar::handle:horizontal {{
    background: {self.p.surface1};
    min-width: 40px;
    border-radius: 4px;
    margin: 2px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {self.p.surface2};
}}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {{
    width: 0;
    background: transparent;
    border: none;
}}
"""

    # ========================
    # Buttons
    # ========================

    def _button_styles(self) -> str:
        r, g, b = self.a.rgb
        return f"""
/* ===== BUTTONS ===== */
QPushButton {{
    background-color: {self.a.hex};
    color: {self.p.crust};
    border: none;
    border-radius: 8px;
    padding: 8px 20px;
    font-weight: 600;
    font-size: 14px;
    min-height: 20px;
}}

QPushButton:hover {{
    background-color: rgba({r}, {g}, {b}, 200);
}}

QPushButton:pressed {{
    background-color: rgba({r}, {g}, {b}, 160);
}}

QPushButton:disabled {{
    background-color: {self.p.surface1};
    color: {self.p.overlay0};
}}

QPushButton#secondaryButton {{
    background-color: {self.p.surface0};
    color: {self.p.text};
}}

QPushButton#secondaryButton:hover {{
    background-color: {self.p.surface1};
}}

QPushButton#dangerButton {{
    background-color: {self.p.red};
    color: {self.p.crust};
}}

QPushButton#dangerButton:hover {{
    background-color: rgba({self._hex_to_rgb_str(self.p.red)}, 200);
}}

QPushButton#ghostButton {{
    background-color: transparent;
    color: {self.p.subtext1};
    padding: 4px 8px;
}}

QPushButton#ghostButton:hover {{
    background-color: {self.p.surface0};
    color: {self.p.text};
}}

QPushButton#iconButton {{
    background-color: transparent;
    border-radius: 6px;
    padding: 6px;
    min-width: 32px;
    max-width: 32px;
    min-height: 32px;
    max-height: 32px;
}}

QPushButton#iconButton:hover {{
    background-color: {self.p.surface0};
}}

QPushButton#iconButton:pressed {{
    background-color: {self.p.surface1};
}}

QPushButton#sendButton {{
    background-color: {self.a.hex};
    border-radius: 20px;
    min-width: 40px;
    max-width: 40px;
    min-height: 40px;
    max-height: 40px;
    padding: 0;
    font-size: 18px;
}}

QPushButton#sendButton:hover {{
    background-color: rgba({r}, {g}, {b}, 200);
}}

QPushButton#sendButton:disabled {{
    background-color: {self.p.surface1};
}}
"""

    # ========================
    # Input Fields
    # ========================

    def _input_styles(self) -> str:
        r, g, b = self.a.rgb
        return f"""
/* ===== INPUT FIELDS ===== */
QLineEdit {{
    background-color: {self.p.surface0};
    color: {self.p.text};
    border: 2px solid transparent;
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 14px;
    selection-background-color: {self.a.hex};
    selection-color: {self.p.crust};
}}

QLineEdit:focus {{
    border-color: {self.a.hex};
}}

QLineEdit:hover {{
    background-color: {self.p.surface1};
}}

QLineEdit::placeholder {{
    color: {self.p.overlay1};
}}

QLineEdit#searchInput {{
    border-radius: 20px;
    padding: 8px 16px 8px 36px;
    background-color: {self.p.surface0};
}}

QLineEdit#searchInput:focus {{
    border-color: {self.a.hex};
    background-color: {self.p.base};
}}

QTextEdit {{
    background-color: {self.p.surface0};
    color: {self.p.text};
    border: 2px solid transparent;
    border-radius: 12px;
    padding: 10px 14px;
    font-size: 14px;
    selection-background-color: {self.a.hex};
    selection-color: {self.p.crust};
}}

QTextEdit:focus {{
    border-color: {self.a.hex};
}}

QTextEdit#messageInput {{
    background-color: {self.p.surface0};
    border-radius: 22px;
    padding: 10px 48px 10px 16px;
    font-size: 14px;
    min-height: 24px;
    max-height: 200px;
}}

QTextEdit#messageInput:focus {{
    border-color: {self.a.hex};
}}
"""

    # ========================
    # Labels
    # ========================

    def _label_styles(self) -> str:
        return f"""
/* ===== LABELS ===== */
QLabel {{
    background: transparent;
    color: {self.p.text};
    border: none;
    padding: 0;
}}

QLabel#titleLabel {{
    font-size: 18px;
    font-weight: 700;
    color: {self.p.text};
}}

QLabel#subtitleLabel {{
    font-size: 12px;
    color: {self.p.subtext0};
}}

QLabel#accentLabel {{
    color: {self.a.hex};
    font-weight: 600;
}}

QLabel#errorLabel {{
    color: {self.p.red};
    font-size: 12px;
}}

QLabel#mutedLabel {{
    color: {self.p.overlay1};
    font-size: 12px;
}}

QLabel#headerLabel {{
    font-size: 16px;
    font-weight: 600;
    color: {self.p.text};
}}

QLabel#timestampLabel {{
    color: {self.p.overlay0};
    font-size: 11px;
}}

QLabel#onlineStatus {{
    color: {self.p.green};
    font-size: 12px;
}}

QLabel#offlineStatus {{
    color: {self.p.overlay0};
    font-size: 12px;
}}

QLabel#typingLabel {{
    color: {self.a.hex};
    font-size: 12px;
    font-style: italic;
}}

QLabel#appTitle {{
    font-size: 20px;
    font-weight: 700;
    color: {self.a.hex};
}}

QLabel#editedLabel {{
    color: {self.p.overlay0};
    font-size: 11px;
    font-style: italic;
}}
"""

    # ========================
    # Sidebar (Chat List)
    # ========================

    def _sidebar_styles(self) -> str:
        r, g, b = self.a.rgb
        return f"""
/* ===== SIDEBAR ===== */
QWidget#sidebar {{
    background-color: {self.p.mantle};
    border-right: 1px solid {self.p.surface0};
}}

QWidget#sidebarHeader {{
    background-color: {self.p.mantle};
    padding: 12px 16px;
    min-height: 48px;
}}

QListWidget#chatList {{
    background-color: {self.p.mantle};
    border: none;
    outline: none;
    padding: 4px 8px;
}}

QListWidget#chatList::item {{
    background-color: transparent;
    border-radius: 8px;
    padding: 10px 12px;
    margin: 2px 0;
    min-height: 48px;
}}

QListWidget#chatList::item:hover {{
    background-color: {self.p.surface0};
}}

QListWidget#chatList::item:selected {{
    background-color: rgba({r}, {g}, {b}, 40);
}}

QListWidget#chatList::item:selected:hover {{
    background-color: rgba({r}, {g}, {b}, 55);
}}

QWidget#chatListItem {{
    background: transparent;
}}

QLabel#chatItemName {{
    font-size: 14px;
    font-weight: 600;
    color: {self.p.text};
}}

QLabel#chatItemPreview {{
    font-size: 12px;
    color: {self.p.subtext0};
}}

QLabel#chatItemTime {{
    font-size: 11px;
    color: {self.p.overlay0};
}}

QLabel#unreadBadge {{
    background-color: {self.a.hex};
    color: {self.p.crust};
    border-radius: 10px;
    padding: 2px 6px;
    font-size: 11px;
    font-weight: 700;
    min-width: 18px;
    min-height: 18px;
    qproperty-alignment: AlignCenter;
}}

QWidget#userListPanel {{
    background-color: {self.p.mantle};
    border-left: 1px solid {self.p.surface0};
}}
"""

    # ========================
    # Chat Header
    # ========================

    def _chat_header_styles(self) -> str:
        return f"""
/* ===== CHAT HEADER ===== */
QWidget#chatHeader {{
    background-color: {self.p.base};
    border-bottom: 1px solid {self.p.surface0};
    padding: 8px 16px;
    min-height: 52px;
    max-height: 52px;
}}

QLabel#chatHeaderName {{
    font-size: 16px;
    font-weight: 600;
    color: {self.p.text};
}}

QLabel#chatHeaderStatus {{
    font-size: 12px;
    color: {self.p.subtext0};
}}
"""

    # ========================
    # Message Input Area
    # ========================

    def _message_input_styles(self) -> str:
        return f"""
/* ===== MESSAGE INPUT AREA ===== */
QWidget#messageInputArea {{
    background-color: {self.p.base};
    border-top: 1px solid {self.p.surface0};
    padding: 8px 16px;
}}

QWidget#replyPreviewBar {{
    background-color: {self.p.surface0};
    border-left: 3px solid {self.a.hex};
    border-radius: 4px;
    padding: 6px 12px;
    margin-bottom: 6px;
}}

QLabel#replyPreviewAuthor {{
    color: {self.a.hex};
    font-weight: 600;
    font-size: 12px;
}}

QLabel#replyPreviewText {{
    color: {self.p.subtext1};
    font-size: 12px;
}}

QPushButton#replyCloseButton {{
    background: transparent;
    border: none;
    color: {self.p.overlay1};
    font-size: 16px;
    padding: 2px;
    min-width: 20px;
    max-width: 20px;
}}

QPushButton#replyCloseButton:hover {{
    color: {self.p.text};
}}

QLabel#charCounter {{
    color: {self.p.overlay0};
    font-size: 11px;
}}

QLabel#charCounterWarning {{
    color: {self.p.yellow};
    font-size: 11px;
    font-weight: 600;
}}

QLabel#charCounterError {{
    color: {self.p.red};
    font-size: 11px;
    font-weight: 700;
}}
"""

    # ========================
    # Context Menu
    # ========================

    def _context_menu_styles(self) -> str:
        return f"""
/* ===== CONTEXT MENU ===== */
QMenu {{
    background-color: {self.p.surface0};
    border: 1px solid {self.p.surface1};
    border-radius: 10px;
    padding: 6px;
}}

QMenu::item {{
    background-color: transparent;
    color: {self.p.text};
    padding: 8px 32px 8px 12px;
    border-radius: 6px;
    margin: 1px 2px;
    font-size: 13px;
}}

QMenu::item:selected {{
    background-color: {self.a.hex};
    color: {self.p.crust};
}}

QMenu::item:disabled {{
    color: {self.p.overlay0};
}}

QMenu::separator {{
    height: 1px;
    background-color: {self.p.surface1};
    margin: 4px 8px;
}}

QMenu::icon {{
    padding-left: 8px;
}}

QWidget#reactionBar {{
    background-color: {self.p.surface0};
    border: 1px solid {self.p.surface1};
    border-radius: 20px;
    padding: 4px 8px;
}}

QPushButton#reactionButton {{
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 4px 6px;
    font-size: 20px;
    min-width: 32px;
    min-height: 32px;
}}

QPushButton#reactionButton:hover {{
    background-color: {self.p.surface1};
}}
"""

    # ========================
    # Dialog
    # ========================

    def _dialog_styles(self) -> str:
        return f"""
/* ===== DIALOGS ===== */
QDialog {{
    background-color: {self.p.base};
    border-radius: 12px;
}}

QDialog QLabel#dialogTitle {{
    font-size: 18px;
    font-weight: 700;
    color: {self.p.text};
    margin-bottom: 8px;
}}

QWidget#dialogOverlay {{
    background-color: rgba(0, 0, 0, 120);
}}
"""

    # ========================
    # Tab Widget
    # ========================

    def _tab_widget_styles(self) -> str:
        r, g, b = self.a.rgb
        return f"""
/* ===== TAB WIDGET ===== */
QTabWidget::pane {{
    border: none;
    background: {self.p.base};
}}

QTabBar::tab {{
    background: transparent;
    color: {self.p.subtext0};
    padding: 10px 20px;
    border: none;
    border-bottom: 2px solid transparent;
    font-size: 14px;
    font-weight: 500;
}}

QTabBar::tab:hover {{
    color: {self.p.text};
    background: {self.p.surface0};
}}

QTabBar::tab:selected {{
    color: {self.a.hex};
    border-bottom-color: {self.a.hex};
    font-weight: 600;
}}
"""

    # ========================
    # Tooltip
    # ========================

    def _tooltip_styles(self) -> str:
        return f"""
/* ===== TOOLTIP ===== */
QToolTip {{
    background-color: {self.p.surface0};
    color: {self.p.text};
    border: 1px solid {self.p.surface1};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
}}
"""

    # ========================
    # Checkbox / Radio
    # ========================

    def _checkbox_radio_styles(self) -> str:
        return f"""
/* ===== CHECKBOX & RADIO ===== */
QCheckBox {{
    color: {self.p.text};
    spacing: 8px;
    font-size: 14px;
}}

QCheckBox::indicator {{
    width: 20px;
    height: 20px;
    border: 2px solid {self.p.surface2};
    border-radius: 4px;
    background: transparent;
}}

QCheckBox::indicator:hover {{
    border-color: {self.a.hex};
}}

QCheckBox::indicator:checked {{
    background-color: {self.a.hex};
    border-color: {self.a.hex};
    image: none;
}}

QRadioButton {{
    color: {self.p.text};
    spacing: 8px;
    font-size: 14px;
}}

QRadioButton::indicator {{
    width: 20px;
    height: 20px;
    border: 2px solid {self.p.surface2};
    border-radius: 10px;
    background: transparent;
}}

QRadioButton::indicator:hover {{
    border-color: {self.a.hex};
}}

QRadioButton::indicator:checked {{
    background-color: {self.a.hex};
    border-color: {self.a.hex};
}}
"""

    # ========================
    # Slider
    # ========================

    def _slider_styles(self) -> str:
        return f"""
/* ===== SLIDER ===== */
QSlider::groove:horizontal {{
    background: {self.p.surface1};
    height: 4px;
    border-radius: 2px;
}}

QSlider::handle:horizontal {{
    background: {self.a.hex};
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
}}

QSlider::handle:horizontal:hover {{
    background: {self.a.hex};
    width: 18px;
    height: 18px;
    margin: -7px 0;
    border-radius: 9px;
}}

QSlider::sub-page:horizontal {{
    background: {self.a.hex};
    border-radius: 2px;
}}
"""

    # ========================
    # Progress Bar
    # ========================

    def _progress_bar_styles(self) -> str:
        return f"""
/* ===== PROGRESS BAR ===== */
QProgressBar {{
    background-color: {self.p.surface0};
    border: none;
    border-radius: 4px;
    height: 8px;
    text-align: center;
    font-size: 0px;
}}

QProgressBar::chunk {{
    background-color: {self.a.hex};
    border-radius: 4px;
}}

QProgressBar#pollProgress {{
    height: 24px;
    border-radius: 6px;
    font-size: 12px;
    color: {self.p.text};
}}

QProgressBar#pollProgress::chunk {{
    border-radius: 6px;
}}
"""

    # ========================
    # Notification Toast
    # ========================

    def _notification_styles(self) -> str:
        return f"""
/* ===== NOTIFICATIONS ===== */
QWidget#notificationToast {{
    background-color: {self.p.surface0};
    border: 1px solid {self.p.surface1};
    border-radius: 12px;
    padding: 12px 16px;
}}

QLabel#notificationTitle {{
    color: {self.p.text};
    font-weight: 600;
    font-size: 13px;
}}

QLabel#notificationBody {{
    color: {self.p.subtext1};
    font-size: 12px;
}}
"""

    # ========================
    # Connection Bar (Moon animation!)
    # ========================

    def _connection_bar_styles(self) -> str:
        return f"""
/* ===== CONNECTION BAR ===== */
QWidget#connectionBar {{
    background-color: {self.p.crust};
    border-top: 1px solid {self.p.surface0};
    min-height: 32px;
    max-height: 32px;
    padding: 0 12px;
}}

QLabel#connectionLabel {{
    color: {self.p.yellow};
    font-size: 12px;
    font-weight: 500;
}}

QLabel#connectionMoon {{
    font-size: 16px;
    min-width: 24px;
}}

QWidget#connectionBarError {{
    background-color: {self.p.crust};
    border-top: 2px solid {self.p.red};
    min-height: 32px;
    max-height: 32px;
    padding: 0 12px;
}}

QLabel#connectionErrorLabel {{
    color: {self.p.red};
    font-size: 12px;
    font-weight: 500;
}}
"""

    # ========================
    # Search
    # ========================

    def _search_styles(self) -> str:
        return f"""
/* ===== SEARCH ===== */
QWidget#searchPanel {{
    background-color: {self.p.base};
    border-bottom: 1px solid {self.p.surface0};
    padding: 8px 16px;
}}

QLabel#searchResultCount {{
    color: {self.p.subtext0};
    font-size: 12px;
}}

QWidget#searchResultItem {{
    background-color: {self.p.surface0};
    border-radius: 8px;
    padding: 8px 12px;
    margin: 4px 0;
}}

QWidget#searchResultItem:hover {{
    background-color: {self.p.surface1};
}}

QLabel#searchHighlight {{
    background-color: {self.a.dimmed(0.3)};
    border-radius: 2px;
    padding: 0 2px;
}}
"""

    # ========================
    # Pinned Bar
    # ========================

    def _pinned_bar_styles(self) -> str:
        return f"""
/* ===== PINNED BAR ===== */
QWidget#pinnedBar {{
    background-color: {self.p.surface0};
    border-bottom: 1px solid {self.p.surface1};
    padding: 6px 16px;
    min-height: 36px;
    max-height: 36px;
}}

QLabel#pinnedIcon {{
    color: {self.a.hex};
    font-size: 14px;
}}

QLabel#pinnedText {{
    color: {self.p.subtext1};
    font-size: 12px;
}}

QPushButton#pinnedButton {{
    background: transparent;
    color: {self.a.hex};
    font-size: 12px;
    font-weight: 600;
    border: none;
    padding: 2px 8px;
}}

QPushButton#pinnedButton:hover {{
    text-decoration: underline;
}}
"""

    # ========================
    # Emoji Picker
    # ========================

    def _emoji_picker_styles(self) -> str:
        return f"""
/* ===== EMOJI PICKER ===== */
QWidget#emojiPicker {{
    background-color: {self.p.surface0};
    border: 1px solid {self.p.surface1};
    border-radius: 12px;
    padding: 8px;
}}

QPushButton#emojiButton {{
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 4px;
    min-width: 36px;
    max-width: 36px;
    min-height: 36px;
    max-height: 36px;
    font-size: 22px;
}}

QPushButton#emojiButton:hover {{
    background-color: {self.p.surface1};
}}

QLabel#emojiCategoryLabel {{
    color: {self.p.subtext0};
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    padding: 8px 4px 4px 4px;
}}
"""

    # ========================
    # Sticker Picker
    # ========================

    def _sticker_picker_styles(self) -> str:
        return f"""
/* ===== STICKER PICKER ===== */
QWidget#stickerPicker {{
    background-color: {self.p.surface0};
    border: 1px solid {self.p.surface1};
    border-radius: 12px;
    padding: 8px;
}}

QPushButton#stickerButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 4px;
    min-width: 80px;
    max-width: 80px;
    min-height: 80px;
    max-height: 80px;
}}

QPushButton#stickerButton:hover {{
    background-color: {self.p.surface1};
    border-color: {self.p.surface2};
}}

QLabel#stickerPackName {{
    color: {self.p.subtext0};
    font-size: 12px;
    font-weight: 600;
    padding: 8px 4px 4px 4px;
}}

QTabBar#stickerPackTabs::tab {{
    padding: 6px 12px;
    font-size: 12px;
}}
"""

    # ========================
    # Poll
    # ========================

    def _poll_styles(self) -> str:
        return f"""
/* ===== POLL ===== */
QWidget#pollWidget {{
    background-color: {self.p.surface0};
    border-radius: 12px;
    padding: 12px;
    border: 1px solid {self.p.surface1};
}}

QLabel#pollQuestion {{
    color: {self.p.text};
    font-size: 15px;
    font-weight: 600;
    margin-bottom: 8px;
}}

QPushButton#pollOption {{
    background-color: {self.p.base};
    color: {self.p.text};
    border: 1px solid {self.p.surface1};
    border-radius: 8px;
    padding: 10px 14px;
    text-align: left;
    font-size: 14px;
    margin: 2px 0;
}}

QPushButton#pollOption:hover {{
    border-color: {self.a.hex};
}}

QPushButton#pollOptionSelected {{
    background-color: {self.a.dimmed(0.15)};
    color: {self.p.text};
    border: 1px solid {self.a.hex};
    border-radius: 8px;
    padding: 10px 14px;
    text-align: left;
    font-size: 14px;
    margin: 2px 0;
}}

QLabel#pollVoteCount {{
    color: {self.p.subtext0};
    font-size: 12px;
}}

QLabel#pollTotalVotes {{
    color: {self.p.overlay1};
    font-size: 12px;
    margin-top: 8px;
}}
"""

    # ========================
    # Reply Preview (in bubble)
    # ========================

    def _reply_preview_styles(self) -> str:
        return f"""
/* ===== REPLY PREVIEW IN BUBBLE ===== */
QWidget#replyInBubble {{
    background-color: rgba(0, 0, 0, 20);
    border-left: 3px solid {self.a.hex};
    border-radius: 4px;
    padding: 4px 8px;
    margin-bottom: 4px;
}}

QLabel#replyInBubbleAuthor {{
    color: {self.a.hex};
    font-size: 12px;
    font-weight: 600;
}}

QLabel#replyInBubbleText {{
    color: {self.p.subtext0};
    font-size: 12px;
}}

QLabel#replyDeletedText {{
    color: {self.p.overlay0};
    font-size: 12px;
    font-style: italic;
}}
"""

    # ========================
    # Settings
    # ========================

    def _settings_styles(self) -> str:
        return f"""
/* ===== SETTINGS ===== */
QWidget#settingsPage {{
    background-color: {self.p.base};
    padding: 24px;
}}

QLabel#settingsSectionTitle {{
    color: {self.p.subtext0};
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
    padding: 16px 0 8px 0;
}}

QWidget#settingsItem {{
    background-color: {self.p.surface0};
    border-radius: 10px;
    padding: 12px 16px;
    margin: 2px 0;
}}

QWidget#settingsItem:hover {{
    background-color: {self.p.surface1};
}}

QWidget#colorPickerItem {{
    min-width: 32px;
    max-width: 32px;
    min-height: 32px;
    max-height: 32px;
    border-radius: 16px;
    border: 2px solid transparent;
}}

QWidget#colorPickerItemSelected {{
    min-width: 32px;
    max-width: 32px;
    min-height: 32px;
    max-height: 32px;
    border-radius: 16px;
    border: 3px solid {self.p.text};
}}
"""

    # ========================
    # Login
    # ========================

    def _login_styles(self) -> str:
        return f"""
/* ===== LOGIN ===== */
QWidget#loginPage {{
    background-color: {self.p.crust};
}}

QWidget#loginCenterWidget {{
    background-color: transparent;
}}

QWidget#loginCard {{
    background-color: {self.p.base};
    border-radius: 16px;
    padding: 40px;
    min-width: 380px;
    max-width: 420px;
}}

QLabel#loginLogo {{
    font-size: 48px;
    margin-bottom: 8px;
}}

QLabel#loginTitle {{
    font-size: 24px;
    font-weight: 700;
    color: {self.p.text};
    margin-bottom: 4px;
}}

QLabel#loginSubtitle {{
    font-size: 14px;
    color: {self.p.subtext0};
    margin-bottom: 24px;
}}

QPushButton#showPasswordButton {{
    background: transparent;
    border: none;
    color: {self.p.overlay1};
    font-size: 16px;
    padding: 0;
    min-width: 24px;
    max-width: 24px;
}}

QPushButton#showPasswordButton:hover {{
    color: {self.p.text};
}}

QLabel#loginLink {{
    color: {self.a.hex};
    font-size: 13px;
}}

QLabel#loginLink:hover {{
    text-decoration: underline;
}}
"""

    # ========================
    # Avatar
    # ========================

    def _avatar_styles(self) -> str:
        return f"""
/* ===== AVATAR ===== */
QLabel#avatar {{
    border-radius: 20px;
    min-width: 40px;
    max-width: 40px;
    min-height: 40px;
    max-height: 40px;
}}

QLabel#avatarLarge {{
    border-radius: 36px;
    min-width: 72px;
    max-width: 72px;
    min-height: 72px;
    max-height: 72px;
}}

QLabel#avatarSmall {{
    border-radius: 14px;
    min-width: 28px;
    max-width: 28px;
    min-height: 28px;
    max-height: 28px;
}}

QWidget#statusDot {{
    border-radius: 6px;
    min-width: 12px;
    max-width: 12px;
    min-height: 12px;
    max-height: 12px;
    border: 2px solid {self.p.mantle};
}}

QWidget#statusDotOnline {{
    background-color: {self.p.green};
}}

QWidget#statusDotAway {{
    background-color: {self.p.yellow};
}}

QWidget#statusDotDnd {{
    background-color: {self.p.red};
}}

QWidget#statusDotOffline {{
    background-color: {self.p.overlay0};
}}
"""

    # ========================
    # Badge
    # ========================

    def _badge_styles(self) -> str:
        return f"""
/* ===== BADGES ===== */
QLabel#badge {{
    background-color: {self.a.hex};
    color: {self.p.crust};
    border-radius: 10px;
    padding: 2px 6px;
    font-size: 11px;
    font-weight: 700;
    min-width: 18px;
    qproperty-alignment: AlignCenter;
}}

QLabel#badgeDanger {{
    background-color: {self.p.red};
}}

QLabel#reactionBadge {{
    background-color: {self.p.surface0};
    border: 1px solid {self.p.surface1};
    border-radius: 12px;
    padding: 2px 8px;
    font-size: 13px;
    min-height: 24px;
}}

QLabel#reactionBadgeActive {{
    background-color: {self.a.dimmed(0.2)};
    border: 1px solid {self.a.hex};
    border-radius: 12px;
    padding: 2px 8px;
    font-size: 13px;
    min-height: 24px;
}}
"""

    # ========================
    # File Preview
    # ========================

    def _file_preview_styles(self) -> str:
        return f"""
/* ===== FILE PREVIEW ===== */
QWidget#filePreview {{
    background-color: {self.p.surface0};
    border: 1px solid {self.p.surface1};
    border-radius: 10px;
    padding: 10px;
}}

QWidget#filePreview:hover {{
    background-color: {self.p.surface1};
}}

QLabel#fileName {{
    color: {self.a.hex};
    font-size: 13px;
    font-weight: 600;
}}

QLabel#fileSize {{
    color: {self.p.subtext0};
    font-size: 11px;
}}

QLabel#fileIcon {{
    font-size: 28px;
    min-width: 40px;
}}

QLabel#imagePreview {{
    border-radius: 8px;
}}
"""

    # ========================
    # Date Separator
    # ========================

    def _date_separator_styles(self) -> str:
        return f"""
/* ===== DATE SEPARATOR ===== */
QWidget#dateSeparator {{
    padding: 16px 0 8px 0;
}}

QLabel#dateSeparatorText {{
    background-color: {self.p.surface0};
    color: {self.p.subtext0};
    font-size: 12px;
    font-weight: 600;
    border-radius: 12px;
    padding: 4px 14px;
}}

QFrame#dateSeparatorLine {{
    background-color: {self.p.surface0};
    max-height: 1px;
    min-height: 1px;
}}

QWidget#unreadSeparator {{
    padding: 8px 0;
}}

QLabel#unreadSeparatorText {{
    background-color: {self.p.red};
    color: {self.p.crust};
    font-size: 11px;
    font-weight: 700;
    border-radius: 10px;
    padding: 3px 12px;
}}

QFrame#unreadSeparatorLine {{
    background-color: {self.p.red};
    max-height: 1px;
    min-height: 1px;
}}
"""

    # ========================
    # Typing Indicator
    # ========================

    def _typing_indicator_styles(self) -> str:
        return f"""
/* ===== TYPING INDICATOR ===== */
QWidget#typingIndicator {{
    background: transparent;
    padding: 2px 16px;
    min-height: 20px;
    max-height: 20px;
}}

QLabel#typingDots {{
    color: {self.a.hex};
    font-size: 14px;
}}
"""

    # ========================
    # Splitter
    # ========================

    def _splitter_styles(self) -> str:
        return f"""
/* ===== SPLITTER ===== */
QSplitter::handle {{
    background-color: {self.p.surface0};
    width: 1px;
}}

QSplitter::handle:hover {{
    background-color: {self.a.hex};
}}
"""

    # ========================
    # ComboBox
    # ========================

    def _combo_box_styles(self) -> str:
        return f"""
/* ===== COMBOBOX ===== */
QComboBox {{
    background-color: {self.p.surface0};
    color: {self.p.text};
    border: 2px solid transparent;
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 14px;
    min-height: 20px;
}}

QComboBox:hover {{
    background-color: {self.p.surface1};
}}

QComboBox:focus {{
    border-color: {self.a.hex};
}}

QComboBox::drop-down {{
    border: none;
    width: 24px;
    padding-right: 8px;
}}

QComboBox QAbstractItemView {{
    background-color: {self.p.surface0};
    color: {self.p.text};
    border: 1px solid {self.p.surface1};
    border-radius: 8px;
    padding: 4px;
    selection-background-color: {self.a.hex};
    selection-color: {self.p.crust};
    outline: none;
}}
"""

    # ========================
    # Helpers
    # ========================

    def _hex_to_rgb_str(self, hex_color: str) -> str:
        """Конвертирует hex в строку 'r, g, b'."""
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"{r}, {g}, {b}"


# ========================
# Convenience Function
# ========================

def generate_stylesheet(palette_name: str = "mocha", accent_name: str = "mauve") -> str:
    """
    Генерирует полный QSS для указанной палитры и акцента.

    Args:
        palette_name: Имя палитры (latte/frappe/macchiato/mocha).
        accent_name: Имя акцентного цвета (mauve/blue/green/...).

    Returns:
        Полная QSS-строка для QApplication.setStyleSheet().
    """
    palette = get_palette(palette_name)
    accent = palette.get_accent(accent_name)
    generator = StyleSheetGenerator(palette, accent)
    return generator.generate()


def get_message_bubble_colors(
        palette_name: str = "mocha",
        accent_name: str = "mauve",
) -> dict:
    """
    Возвращает цвета для пузырьков сообщений.
    Используется в MessageDelegate для рисования через QPainter.

    Returns:
        Словарь с цветами для своих и чужих пузырьков.
    """
    p = get_palette(palette_name)
    a = p.get_accent(accent_name)
    ar, ag, ab = a.rgb

    return {
        # Свой пузырёк (справа)
        "own_bubble_bg": f"rgba({ar}, {ag}, {ab}, 35)",
        "own_bubble_bg_hover": f"rgba({ar}, {ag}, {ab}, 50)",
        "own_bubble_border": f"rgba({ar}, {ag}, {ab}, 60)",

        # Чужой пузырёк (слева)
        "other_bubble_bg": p.surface0,
        "other_bubble_bg_hover": p.surface1,
        "other_bubble_border": p.surface1,

        # Текст
        "text_color": p.text,
        "subtext_color": p.subtext0,
        "timestamp_color": p.overlay0,
        "link_color": a.hex,

        # Спойлер
        "spoiler_bg": p.surface2,
        "spoiler_bg_revealed": "transparent",

        # Код
        "code_bg": p.mantle,
        "code_border": p.surface0,
        "code_text": p.text,

        # Reply bar
        "reply_bar_color": a.hex,
        "reply_bg": "rgba(0, 0, 0, 15)",

        # Forwarded
        "forwarded_color": p.subtext0,

        # Edited
        "edited_color": p.overlay0,

        # Selection
        "selection_bg": f"rgba({ar}, {ag}, {ab}, 40)",

        # Палитра и акцент (для доступа в delegate)
        "palette": p,
        "accent": a,
    }