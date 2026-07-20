"""
Lantern v2 — Chat View
QListView с кастомным делегатом для отображения сообщений.

Ключевые фичи:
- Пагинация при скролле вверх (подгрузка старых сообщений)
- Автоскролл при новых сообщениях (если пользователь внизу)
- Пустой чат — сообщения начинаются СВЕРХУ (не по центру, не снизу)
- Правильная обработка ресайза (пересчёт sizeHint)
- Клик по reply → скролл к оригиналу
- ПКМ → контекстное меню
"""

import asyncio
from typing import Optional

from PyQt5.QtWidgets import (
    QListView, QWidget, QVBoxLayout, QAbstractItemView,
    QApplication, QLabel, QHBoxLayout, QScroller
)
from PyQt5.QtGui import (
    QPainter, QColor, QFont, QWheelEvent, QMouseEvent,
    QResizeEvent, QCursor
)
from PyQt5.QtCore import (
    Qt, QModelIndex, QSize, QTimer, QPoint,
    pyqtSignal, QRect, QItemSelectionModel, QVariant
)

from client.ui.components.message_model import MessageModel, MessageRole
from client.ui.components.message_delegate import MessageDelegate
from client.ui.components.context_menu import MessageContextMenu
from client.themes.catppuccin import Palette, AccentColor


class ChatView(QWidget):
    """
    Виджет отображения чата.

    Содержит:
    - QListView с MessageDelegate
    - Логику пагинации
    - Логику автоскролла
    - Обработку ПКМ и кликов
    """

    # Сигналы
    load_more_requested = pyqtSignal()
    reply_requested = pyqtSignal(dict)
    edit_requested = pyqtSignal(dict)
    delete_requested = pyqtSignal(str, bool)
    reaction_requested = pyqtSignal(str, str)
    pin_requested = pyqtSignal(str, bool)
    forward_requested = pyqtSignal(list)
    copy_text_requested = pyqtSignal(str)
    save_file_requested = pyqtSignal(dict)
    open_in_folder_requested = pyqtSignal(dict)
    copy_image_requested = pyqtSignal(dict)
    scroll_to_message_requested = pyqtSignal(str)
    message_visible = pyqtSignal(str)

    def __init__(
        self,
        palette: Palette,
        accent: AccentColor,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)

        self._palette = palette
        self._accent = accent
        self._current_user_id = ""
        self._current_chat_id = ""
        self._is_loading_more = False
        self._has_more_messages = True
        self._is_at_bottom = True
        self._selected_messages: list[str] = []

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Инициализация UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # === List View ===
        self._list_view = _ChatListView(self)
        self._list_view.setObjectName("chatMessages")
        self._list_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list_view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self._list_view.setSelectionMode(QAbstractItemView.NoSelection)
        self._list_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._list_view.setFocusPolicy(Qt.NoFocus)
        self._list_view.setMouseTracking(True)
        self._list_view.setAttribute(Qt.WA_Hover, True)
        self._list_view.setUniformItemSizes(False)
        self._list_view.setSpacing(0)
        self._list_view.setWordWrap(False)
        self._list_view.setFrameShape(QListView.NoFrame)

        # Стиль фона
        self._list_view.setStyleSheet(
            f"QListView {{ background-color: {self._palette.base}; border: none; }}"
            f"QListView::item {{ border: none; padding: 0; }}"
        )

        # Модель
        self._model = MessageModel()
        self._list_view.setModel(self._model)

        # Делегат
        self._delegate = MessageDelegate(
            palette=self._palette,
            accent=self._accent,
        )
        self._list_view.setItemDelegate(self._delegate)

        # Скроллбар
        scrollbar = self._list_view.verticalScrollBar()
        scrollbar.valueChanged.connect(self._on_scroll)
        scrollbar.rangeChanged.connect(self._on_scroll_range_changed)

        # Smooth scrolling — безопасная инициализация
        self._init_smooth_scrolling()

        # Контекстное меню
        self._list_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self._list_view.customContextMenuRequested.connect(self._on_context_menu)

        # Клик по сообщению
        self._list_view.clicked.connect(self._on_item_clicked)

        layout.addWidget(self._list_view, 1)

        # === Empty state label ===
        self._empty_label = QLabel("💬 Начните общение!", self)
        self._empty_label.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        self._empty_label.setStyleSheet(
            f"color: {self._palette.overlay0}; font-size: 16px; "
            f"padding-top: 60px; font-weight: 500; background: transparent;"
        )
        self._empty_label.setVisible(False)
        self._empty_label.raise_()

        # Модельные сигналы
        self._model.messages_loaded.connect(self._on_messages_loaded)
        self._model.message_added.connect(self._on_message_added)

    def _init_smooth_scrolling(self) -> None:
        """
        Инициализация smooth scrolling.
        НЕ используем QScroller.grabGesture с LeftMouseButtonGesture,
        потому что это перехватывает клики и ломает контекстное меню.
        Плавный скролл обеспечивается кастомным wheelEvent в _ChatListView.
        """
        pass

    # ========================
    # Public API
    # ========================

    def set_current_user(self, user_id: str) -> None:
        """Устанавливает текущего пользователя."""
        self._current_user_id = user_id
        self._model.set_current_user(user_id)
        self._delegate.set_current_user(user_id)

    def set_theme(self, palette: Palette, accent: AccentColor) -> None:
        """Обновляет тему."""
        self._palette = palette
        self._accent = accent
        self._delegate.set_theme(palette, accent)
        self._list_view.setStyleSheet(
            f"QListView {{ background-color: {palette.base}; border: none; }}"
            f"QListView::item {{ border: none; padding: 0; }}"
        )
        self._empty_label.setStyleSheet(
            f"color: {palette.overlay0}; font-size: 16px; "
            f"padding-top: 60px; font-weight: 500;"
        )
        self._list_view.viewport().update()

    def load_chat(
        self,
        chat_id: str,
        messages: list[dict],
        last_read_message_id: Optional[str] = None,
        unread_count: int = 0,
    ) -> None:
        """
        Загружает чат: очищает старые данные, загружает сообщения.
        """
        self._current_chat_id = chat_id
        self._has_more_messages = True
        self._is_loading_more = False

        if last_read_message_id is None and unread_count > 0 and messages:
            # Вычисляем last_read из количества непрочитанных
            real_messages = [m for m in messages if m.get("id")]
            if unread_count < len(real_messages):
                last_read_message_id = real_messages[-(unread_count + 1)].get("id")

        self._model.set_last_read_message_id(last_read_message_id)
        self._model.load_messages(messages)

        # Показываем/скрываем пустое состояние
        is_empty = self._model.is_empty()
        self._empty_label.setVisible(is_empty)
        self._list_view.setVisible(not is_empty)
        if is_empty:
            self._empty_label.raise_()
            self._update_empty_label_geometry()

        if not is_empty:
            self._scroll_to_unread_or_bottom()

    def prepend_messages(self, messages: list[dict]) -> None:
        """Добавляет старые сообщения (при скролле вверх)."""
        if not messages:
            self._has_more_messages = False
            self._is_loading_more = False
            return

        scrollbar = self._list_view.verticalScrollBar()
        old_max = scrollbar.maximum()
        old_value = scrollbar.value()

        self._model.prepend_messages(messages)

        QTimer.singleShot(10, lambda: self._restore_scroll_position(old_max, old_value))

        self._is_loading_more = False

        if len(messages) < 50:
            self._has_more_messages = False

    def append_message(self, message: dict) -> None:
        """Добавляет новое сообщение."""
        was_empty = self._model.is_empty()

        self._model.append_message(message)

        if was_empty:
            self._empty_label.setVisible(False)
            self._list_view.setVisible(True)

        if self._is_at_bottom:
            QTimer.singleShot(50, self._scroll_to_bottom)

    def update_message(self, message_id: str, updates: dict) -> None:
        """Обновляет сообщение."""
        self._model.update_message(message_id, updates)
        self._invalidate_message(message_id)

    def delete_message(self, message_id: str, for_everyone: bool) -> None:
        """Удаляет сообщение."""
        self._model.delete_message(message_id, for_everyone)
        self._delegate.invalidate_message_cache(message_id)

    def update_reactions(self, message_id: str, reactions: list[dict]) -> None:
        """Обновляет реакции."""
        self._model.update_reactions(message_id, reactions)
        self._invalidate_message(message_id)

    def mark_edited(self, message_id: str, new_content: str) -> None:
        """Помечает как отредактированное."""
        self._model.mark_edited(message_id, new_content)
        self._invalidate_message(message_id)

    def mark_pinned(self, message_id: str, pinned: bool) -> None:
        """Закрепляет/открепляет."""
        self._model.mark_pinned(message_id, pinned)
        self._invalidate_message(message_id)

    def update_poll(self, message_id: str, poll_data: dict) -> None:
        """Обновляет опрос."""
        self._model.update_poll(message_id, poll_data)
        self._invalidate_message(message_id)

    def _invalidate_message(self, message_id: str) -> None:
        """Сбрасывает кэш делегата и пересчитывает layout для сообщения."""
        self._delegate.invalidate_message_cache(message_id)
        idx = self._model.get_message_index(message_id)
        if idx is not None:
            model_index = self._model.index(idx)
            self._list_view.update(model_index)
            self._list_view.doItemsLayout()

    def scroll_to_message(self, message_id: str) -> None:
        """Скроллит к сообщению."""
        idx = self._model.get_message_index(message_id)
        if idx is not None:
            model_index = self._model.index(idx)
            self._list_view.scrollTo(model_index, QAbstractItemView.PositionAtCenter)

    def get_first_message_id(self) -> Optional[str]:
        return self._model.get_first_message_id()

    def get_last_message_id(self) -> Optional[str]:
        return self._model.get_last_message_id()

    def clear_chat(self) -> None:
        """Очищает чат."""
        self._model.clear_all()
        self._empty_label.setVisible(True)
        self._list_view.setVisible(False)

    @property
    def model(self) -> MessageModel:
        return self._model

    # ========================
    # Scrolling
    # ========================

    def _on_scroll(self, value: int) -> None:
        scrollbar = self._list_view.verticalScrollBar()
        self._is_at_bottom = (value >= scrollbar.maximum() - 50)

        if value <= 10 and self._has_more_messages and not self._is_loading_more:
            self._is_loading_more = True
            self.load_more_requested.emit()

        self._check_visible_messages()

    def _on_scroll_range_changed(self, min_val: int, max_val: int) -> None:
        pass

    def _scroll_to_bottom(self) -> None:
        scrollbar = self._list_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _scroll_to_unread_or_bottom(self) -> None:
        for i in range(self._model.rowCount()):
            index = self._model.index(i)
            item_type = self._model.data(index, MessageRole.ItemType)
            if item_type == "unread_separator":
                QTimer.singleShot(50, lambda idx=i: self._list_view.scrollTo(
                    self._model.index(idx),
                    QAbstractItemView.PositionAtTop,
                ))
                return

        QTimer.singleShot(50, self._scroll_to_bottom)

    def _restore_scroll_position(self, old_max: int, old_value: int) -> None:
        scrollbar = self._list_view.verticalScrollBar()
        new_max = scrollbar.maximum()
        delta = new_max - old_max
        scrollbar.setValue(old_value + delta)

    def _check_visible_messages(self) -> None:
        viewport = self._list_view.viewport()
        viewport_rect = viewport.rect()

        bottom_point = QPoint(viewport_rect.center().x(), viewport_rect.bottom() - 5)
        index = self._list_view.indexAt(bottom_point)

        if index.isValid():
            item_type = index.data(MessageRole.ItemType)
            if item_type == "message":
                msg_id = index.data(MessageRole.MessageId)
                if msg_id:
                    self.message_visible.emit(msg_id)

    # ========================
    # Model Signals
    # ========================

    def _on_messages_loaded(self) -> None:
        self._delegate.invalidate_cache()

    def _on_message_added(self, message_id: str) -> None:
        pass

    # ========================
    # Context Menu
    # ========================

    def _on_context_menu(self, pos: QPoint) -> None:
        index = self._list_view.indexAt(pos)
        if not index.isValid():
            return

        item_type = index.data(MessageRole.ItemType)
        if item_type != "message":
            return

        msg_data = index.data(MessageRole.MessageData)
        if not msg_data:
            return

        is_deleted = index.data(MessageRole.IsDeleted)
        if is_deleted:
            return

        is_own = index.data(MessageRole.IsOwn)
        file_att = index.data(MessageRole.FileAttachment)
        is_pinned = index.data(MessageRole.IsPinned)

        has_file = file_att is not None
        is_image = False
        if file_att:
            mime = file_att.get("mime_type", "")
            is_image = mime.startswith("image/")

        menu = MessageContextMenu(
            is_own_message=is_own,
            has_file=has_file,
            is_image=is_image,
            is_pinned=is_pinned,
            parent=self,
        )

        msg_id = index.data(MessageRole.MessageId)
        content = index.data(MessageRole.Content) or ""

        menu.reply_requested.connect(lambda: self.reply_requested.emit(msg_data))
        menu.edit_requested.connect(lambda: self.edit_requested.emit(msg_data))
        menu.delete_requested.connect(lambda fe: self.delete_requested.emit(msg_id, fe))
        menu.reaction_requested.connect(lambda emoji: self.reaction_requested.emit(msg_id, emoji))
        menu.pin_requested.connect(lambda: self.pin_requested.emit(msg_id, not is_pinned))
        menu.forward_requested.connect(lambda: self.forward_requested.emit([msg_data]))
        menu.copy_requested.connect(lambda: self._copy_to_clipboard(content))

        if has_file:
            menu.save_file_requested.connect(lambda: self.save_file_requested.emit(file_att))
            menu.open_in_folder_requested.connect(
                lambda: self.open_in_folder_requested.emit(file_att)
            )
            if is_image:
                menu.copy_image_requested.connect(
                    lambda: self.copy_image_requested.emit(file_att)
                )

        menu.show_at_cursor()

    def _copy_to_clipboard(self, text: str) -> None:
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(text)

    # ========================
    # Click Handling
    # ========================

    def _on_item_clicked(self, index: QModelIndex) -> None:
        if not index.isValid():
            return

        item_type = index.data(MessageRole.ItemType)
        if item_type != "message":
            return

    # ========================
    # Resize
    # ========================

    def _update_empty_label_geometry(self) -> None:
        """Позиционирует empty-state поверх списка сообщений."""
        if self._empty_label.isVisible():
            self._empty_label.setGeometry(self._list_view.geometry())
            self._empty_label.raise_()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._delegate.invalidate_cache()
        self._update_empty_label_geometry()
        self._list_view.doItemsLayout()


class _ChatListView(QListView):
    """
    Кастомный QListView для чата.
    Переопределяет поведение скролла.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Плавный скролл колёсиком мыши."""
        delta = event.angleDelta().y()
        pixels = int(delta * 0.6)
        scrollbar = self.verticalScrollBar()
        scrollbar.setValue(scrollbar.value() - pixels)
        event.accept()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        delegate = self.itemDelegate()
        if isinstance(delegate, MessageDelegate):
            delegate.invalidate_cache()
            self.doItemsLayout()
