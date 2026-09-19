"""
Lantern v2 — Context Menu
Кастомное контекстное меню с эмодзи-иконками и полосой быстрых реакций.
Красивое, анимированное, pixel-perfect.
"""

from typing import Optional, Callable
from client.themes.fonts import get_font_family

from PyQt5.QtWidgets import (
    QMenu, QAction, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QWidgetAction, QLabel, QFrame, QGraphicsOpacityEffect
)
from PyQt5.QtGui import QCursor, QFont, QColor, QPainter, QPainterPath, QIcon
from PyQt5.QtCore import Qt, QPoint, QPropertyAnimation, QEasingCurve, QSize, pyqtSignal, QTimer

# Быстрые реакции (топ-6 + кнопка "ещё")
QUICK_REACTIONS = ["😂", "❤️", "👍", "😮", "😢", "🔥"]

# Полный набор реакций (30 штук)
ALL_REACTIONS = [
    "😂", "❤️", "👍", "😮", "😢", "🔥",
    "🥰", "😎", "🤔", "👀", "🎉", "💯",
    "😭", "🙏", "💀", "✨", "🤣", "😍",
    "🫡", "💔", "😡", "🤡", "👎", "💪",
    "🤝", "😈", "🥳", "🫠", "😤", "❤️‍🔥",
]


class ReactionBarWidget(QWidget):
    """
    Горизонтальная полоса быстрых реакций.
    Отображается над пунктами контекстного меню.
    """

    reaction_selected = pyqtSignal(str)  # emoji

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("reactionBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        for emoji in QUICK_REACTIONS:
            btn = QPushButton(emoji)
            btn.setObjectName("reactionButton")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(f"Реакция {emoji}")
            btn.setFont(QFont(get_font_family("emoji"), 16))
            btn.clicked.connect(lambda checked, e=emoji: self.reaction_selected.emit(e))
            layout.addWidget(btn)

        # Кнопка "ещё"
        more_btn = QPushButton("➕")
        more_btn.setObjectName("reactionButton")
        more_btn.setCursor(Qt.PointingHandCursor)
        more_btn.setToolTip("Все реакции")
        more_btn.setFont(QFont(get_font_family("emoji"), 14))
        more_btn.clicked.connect(lambda: self.reaction_selected.emit("__more__"))
        layout.addWidget(more_btn)


class ExpandedReactionPicker(QWidget):
    """
    Расширенный пикер реакций (30 штук).
    Появляется при нажатии "➕".
    """

    reaction_selected = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("emojiPicker")
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # Заголовок
        title = QLabel("Выберите реакцию")
        title.setObjectName("emojiCategoryLabel")
        layout.addWidget(title)

        # Сетка реакций (6 колонок)
        grid_widget = QWidget()
        grid_layout = QHBoxLayout(grid_widget)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setSpacing(0)

        columns = [QVBoxLayout() for _ in range(6)]
        for col in columns:
            col.setSpacing(0)

        for i, emoji in enumerate(ALL_REACTIONS):
            col_idx = i % 6
            btn = QPushButton(emoji)
            btn.setObjectName("emojiButton")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFont(QFont(get_font_family("emoji"), 16))
            btn.clicked.connect(lambda checked, e=emoji: self._select(e))
            columns[col_idx].addWidget(btn)

        for col in columns:
            col_widget = QWidget()
            col_widget.setLayout(col)
            grid_layout.addWidget(col_widget)

        layout.addWidget(grid_widget)

    def _select(self, emoji: str) -> None:
        self.reaction_selected.emit(emoji)
        self.close()


class MessageContextMenu(QMenu):
    """
    Контекстное меню сообщения с эмодзи-иконками.

    Адаптируется в зависимости от:
    - Своё/чужое сообщение
    - Наличие файла
    - Тип файла (изображение или нет)
    """

    # Сигналы действий
    reply_requested = pyqtSignal()
    edit_requested = pyqtSignal()
    pin_requested = pyqtSignal()
    copy_requested = pyqtSignal()
    forward_requested = pyqtSignal()
    delete_requested = pyqtSignal(bool)  # for_everyone
    reaction_requested = pyqtSignal(str)  # emoji
    save_file_requested = pyqtSignal()
    open_in_folder_requested = pyqtSignal()
    copy_image_requested = pyqtSignal()

    def __init__(
            self,
            is_own_message: bool,
            has_file: bool = False,
            is_image: bool = False,
            is_pinned: bool = False,
            parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)

        self._is_own = is_own_message
        self._has_file = has_file
        self._is_image = is_image
        self._is_pinned = is_pinned

        self._reaction_picker: Optional[ExpandedReactionPicker] = None

        self._build_menu()

    def _build_menu(self) -> None:
        """Строит меню с эмодзи-иконками."""

        # === Полоса быстрых реакций (вверху) ===
        reaction_bar = ReactionBarWidget()
        reaction_bar.reaction_selected.connect(self._on_reaction)

        reaction_action = QWidgetAction(self)
        reaction_action.setDefaultWidget(reaction_bar)
        self.addAction(reaction_action)

        self.addSeparator()

        # === Основные действия ===
        self._add_action("↩️", "Ответить", self.reply_requested.emit)

        if self._is_own:
            self._add_action("✏️", "Редактировать", self.edit_requested.emit)

        pin_text = "📌  Открепить" if self._is_pinned else "📌  Закрепить"
        pin_emoji = "📌"
        self._add_action(pin_emoji, "Открепить" if self._is_pinned else "Закрепить",
                         self.pin_requested.emit)

        self._add_action("📋", "Копировать текст", self.copy_requested.emit)
        self._add_action("↗️", "Переслать", self.forward_requested.emit)

        # === Файловые действия ===
        if self._has_file:
            self.addSeparator()
            self._add_action("💾", "Сохранить как...", self.save_file_requested.emit)
            self._add_action("📂", "Открыть в папке", self.open_in_folder_requested.emit)

            if self._is_image:
                self._add_action("🖼️", "Копировать изображение",
                                 self.copy_image_requested.emit)

        # === Удаление ===
        self.addSeparator()

        if self._is_own:
            delete_action = self._add_action(
                "🗑️", "Удалить для всех",
                lambda: self.delete_requested.emit(True),
            )
            # Стилизуем красным через шрифт
        else:
            self._add_action(
                "🗑️", "Удалить для себя",
                lambda: self.delete_requested.emit(False),
            )

    def _add_action(
            self,
            emoji: str,
            text: str,
            callback: Callable,
    ) -> QAction:
        """Добавляет пункт меню с эмодзи-иконкой."""
        action = QAction(f"{emoji}  {text}", self)
        action.setFont(QFont(get_font_family("ui"), 13))
        action.triggered.connect(callback)
        action.triggered.connect(self.close)
        self.addAction(action)
        return action

    def _on_reaction(self, emoji: str) -> None:
        """Обработка выбора реакции."""
        if emoji == "__more__":
            # Показываем расширенный пикер
            self._reaction_picker = ExpandedReactionPicker()
            self._reaction_picker.reaction_selected.connect(self._on_expanded_reaction)

            # Позиционируем рядом с меню
            pos = self.pos()
            self._reaction_picker.move(pos.x() + self.width() + 4, pos.y())
            self._reaction_picker.show()
        else:
            self.reaction_requested.emit(emoji)
            self.close()

    def _on_expanded_reaction(self, emoji: str) -> None:
        """Обработка выбора из расширенного пикера."""
        self.reaction_requested.emit(emoji)
        self.close()

    def show_at_cursor(self) -> None:
        """Показывает меню в позиции курсора."""
        self.popup(QCursor.pos())
