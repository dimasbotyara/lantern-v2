"""
Lantern v2 — Emoji Picker Widget
Полноценный пикер эмодзи с категориями, поиском и рендером через Segoe UI Emoji / Noto.
"""

from typing import Optional
from client.themes.fonts import get_font_family

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QLineEdit, QScrollArea,
    QTabWidget, QFrame
)
from PyQt5.QtCore import Qt, QSize, pyqtSignal
from PyQt5.QtGui import QFont

# Категории эмодзи с полным набором
EMOJI_CATEGORIES = {
    "😊 Частые": [
        "😀", "😃", "😄", "😁", "😅", "😂", "🤣", "😊",
        "😇", "🙂", "😉", "😌", "😍", "🥰", "😘", "😗",
        "😙", "😚", "😋", "😛", "😜", "🤪", "😝", "🤑",
        "🤗", "🤭", "🤫", "🤔", "🤐", "🤨", "😐", "😑",
        "😶", "😏", "😒", "🙄", "😬", "🤥", "😌", "😔",
        "😪", "🤤", "😴", "😷", "🤒", "🤕", "🤢", "🤮",
    ],
    "❤️ Символы": [
        "❤️", "🧡", "💛", "💚", "💙", "💜", "🖤", "🤍",
        "🤎", "💔", "❤️‍🔥", "❤️‍🩹", "💕", "💞", "💓", "💗",
        "💖", "💘", "💝", "💟", "☮️", "✝️", "☪️", "🕉️",
        "☯️", "✡️", "🔯", "🕎", "☸️", "⚛️", "🛐", "⭐",
        "🌟", "💫", "✨", "⚡", "🔥", "💥", "☀️", "🌈",
    ],
    "👋 Жесты": [
        "👋", "🤚", "🖐️", "✋", "🖖", "👌", "🤌", "🤏",
        "✌️", "🤞", "🤟", "🤘", "🤙", "👈", "👉", "👆",
        "🖕", "👇", "☝️", "👍", "👎", "✊", "👊", "🤛",
        "🤜", "👏", "🙌", "👐", "🤲", "🤝", "🙏", "💪",
    ],
    "🐱 Животные": [
        "🐱", "🐶", "🐭", "🐹", "🐰", "🦊", "🐻", "🐼",
        "🐨", "🐯", "🦁", "🐮", "🐷", "🐸", "🐵", "🙈",
        "🙉", "🙊", "🐔", "🐧", "🐦", "🐤", "🦆", "🦅",
        "🦉", "🦇", "🐺", "🐗", "🐴", "🦄", "🐝", "🐛",
        "🦋", "🐌", "🐞", "🐜", "🦟", "🦗", "🐢", "🐍",
    ],
    "🍔 Еда": [
        "🍎", "🍐", "🍊", "🍋", "🍌", "🍉", "🍇", "🍓",
        "🫐", "🍈", "🍒", "🍑", "🥭", "🍍", "🥥", "🥝",
        "🍅", "🍆", "🥑", "🥦", "🥬", "🌶️", "🫑", "🥒",
        "🍔", "🍟", "🍕", "🌭", "🥪", "🌮", "🌯", "🥙",
        "🍳", "🥘", "🍲", "🥗", "🍿", "🧈", "🧂", "🥫",
        "☕", "🍵", "🍺", "🍻", "🥂", "🍷", "🍸", "🍹",
    ],
    "⚽ Активности": [
        "⚽", "🏀", "🏈", "⚾", "🥎", "🎾", "🏐", "🏉",
        "🥏", "🎱", "🪀", "🏓", "🏸", "🏒", "🥅", "⛳",
        "🎣", "🤿", "🎿", "⛷️", "🏂", "🪂", "🏋️", "🤸",
        "🎮", "🕹️", "🎲", "🧩", "♟️", "🎯", "🎳", "🎪",
        "🎨", "🎭", "🎬", "🎤", "🎧", "🎼", "🎹", "🥁",
    ],
    "🚗 Путешествия": [
        "🚗", "🚕", "🚙", "🚌", "🚎", "🏎️", "🚓", "🚑",
        "🚒", "🚐", "🛻", "🚚", "🚛", "🚜", "🛵", "🏍️",
        "🚲", "🛴", "🚂", "🚆", "🚇", "🚊", "✈️", "🚀",
        "🛸", "🚁", "⛵", "🚢", "🗼", "🏰", "🏠", "🏢",
    ],
    "💡 Объекты": [
        "💡", "🔦", "🕯️", "💰", "💎", "🔧", "🔨", "⚙️",
        "🔩", "🧲", "💊", "🩹", "🩺", "🔬", "🔭", "📡",
        "💻", "🖥️", "⌨️", "🖱️", "📱", "☎️", "📷", "📹",
        "📺", "📻", "⏰", "📅", "📌", "📎", "✂️", "📝",
        "📁", "📂", "🗂️", "📊", "📈", "🔒", "🔑", "🏮",
    ],
    "🏁 Флаги": [
        "🏳️", "🏴", "🏁", "🚩", "🏳️‍🌈", "🏳️‍⚧️", "🇺🇳",
        "🇷🇺", "🇺🇸", "🇬🇧", "🇩🇪", "🇫🇷", "🇯🇵", "🇰🇷",
        "🇨🇳", "🇧🇷", "🇮🇳", "🇮🇹", "🇪🇸", "🇨🇦", "🇦🇺",
        "🇺🇦", "🇵🇱", "🇹🇷", "🇲🇽", "🇦🇷", "🇳🇱", "🇸🇪",
    ],
}


class EmojiPicker(QWidget):
    """
    Полноценный пикер эмодзи с:
    - Категориями (вкладки)
    - Поиском
    - Крупным рендером через Segoe UI Emoji / Noto Color Emoji

    Используется для:
    - Вставки эмодзи в сообщение
    - Выбора реакций
    """

    emoji_selected = pyqtSignal(str)  # Unicode emoji string

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("emojiPicker")
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)

        self.setFixedSize(380, 420)
        self._build_ui()

    def _build_ui(self) -> None:
        """Строит интерфейс пикера."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # === Поиск ===
        self._search_input = QLineEdit()
        self._search_input.setObjectName("searchInput")
        self._search_input.setPlaceholderText("🔍 Поиск эмодзи...")
        self._search_input.textChanged.connect(self._on_search)
        layout.addWidget(self._search_input)

        # === Вкладки категорий ===
        self._tab_widget = QTabWidget()
        self._tab_widget.setObjectName("emojiTabs")
        self._tab_widget.setTabPosition(QTabWidget.South)

        # Emoji font
        self._emoji_font = QFont(get_font_family("emoji"), 20)
        self._tab_font = QFont(get_font_family("emoji"), 14)

        for category_name, emojis in EMOJI_CATEGORIES.items():
            scroll = self._create_emoji_grid(emojis)
            tab_icon = category_name.split(" ")[0]  # Берём эмодзи из названия
            self._tab_widget.addTab(scroll, tab_icon)

        layout.addWidget(self._tab_widget, 1)

        # === Результаты поиска (скрыты по умолчанию) ===
        self._search_scroll = self._create_emoji_grid([])
        self._search_scroll.setVisible(False)
        layout.addWidget(self._search_scroll, 1)

    def _create_emoji_grid(self, emojis: list[str]) -> QScrollArea:
        """Создаёт сетку эмодзи в скролле."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        grid = QGridLayout(container)
        grid.setContentsMargins(4, 4, 4, 4)
        grid.setSpacing(2)

        cols = 8  # 8 колонок

        for i, emoji in enumerate(emojis):
            btn = QPushButton(emoji)
            btn.setObjectName("emojiButton")
            btn.setFont(self._emoji_font)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(emoji)
            btn.clicked.connect(lambda checked, e=emoji: self._select_emoji(e))

            row = i // cols
            col = i % cols
            grid.addWidget(btn, row, col)

        # Заполняем оставшиеся ячейки пустыми виджетами
        total = len(emojis)
        remaining = cols - (total % cols) if total % cols != 0 else 0
        for i in range(remaining):
            spacer = QWidget()
            spacer.setFixedSize(36, 36)
            grid.addWidget(spacer, total // cols, (total % cols) + i)

        scroll.setWidget(container)
        return scroll

    def _select_emoji(self, emoji: str) -> None:
        """Обработка выбора эмодзи."""
        self.emoji_selected.emit(emoji)
        self.close()

    def _on_search(self, query: str) -> None:
        """Фильтрация эмодзи по поиску."""
        query = query.strip().lower()

        if not query:
            self._tab_widget.setVisible(True)
            self._search_scroll.setVisible(False)
            return

        # Собираем все эмодзи
        all_emojis = []
        for emojis in EMOJI_CATEGORIES.values():
            all_emojis.extend(emojis)

        # Простой поиск (по самому эмодзи)
        # В будущем можно добавить поиск по описаниям
        filtered = [e for e in all_emojis if query in e]

        # Пересоздаём поисковый грид
        self._tab_widget.setVisible(False)

        # Удаляем старый search_scroll
        parent_layout = self.layout()
        if self._search_scroll:
            self._search_scroll.setVisible(False)
            parent_layout.removeWidget(self._search_scroll)
            self._search_scroll.deleteLater()

        self._search_scroll = self._create_emoji_grid(filtered)
        self._search_scroll.setVisible(True)
        parent_layout.addWidget(self._search_scroll, 1)

    def show_at(self, pos) -> None:
        """Показывает пикер в указанной позиции."""
        self.move(pos)
        self.show()
        self._search_input.setFocus()
        self._search_input.clear()
