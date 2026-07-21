"""
Lantern v2 — Message Data Model
QAbstractListModel для хранения сообщений.
Поддерживает: вставку новых, редактирование, удаление, пагинацию,
разделители дат, метку непрочитанных.
"""

import json
from datetime import datetime, timezone, timedelta
from typing import Optional, Any
from enum import IntEnum

from PyQt5.QtCore import (
    Qt, QAbstractListModel, QModelIndex, QVariant,
    pyqtSignal, QSize
)

from client.utils.helpers import format_date_separator


class MessageRole(IntEnum):
    """Кастомные роли для данных сообщений."""
    MessageData = Qt.UserRole + 1  # Полный dict сообщения
    MessageId = Qt.UserRole + 2  # str: ID
    ChatId = Qt.UserRole + 3  # str: ID чата
    AuthorData = Qt.UserRole + 4  # dict: автор
    Content = Qt.UserRole + 5  # str: расшифрованный текст
    MessageType = Qt.UserRole + 6  # str: text/file/sticker/poll/system
    Timestamp = Qt.UserRole + 7  # str: ISO timestamp
    IsOwn = Qt.UserRole + 8  # bool: своё сообщение
    IsEdited = Qt.UserRole + 9  # bool
    IsDeleted = Qt.UserRole + 10  # bool
    ReplyTo = Qt.UserRole + 11  # dict или None
    ForwardedFrom = Qt.UserRole + 12  # dict или None
    Reactions = Qt.UserRole + 13  # list[dict]
    FileAttachment = Qt.UserRole + 14  # dict или None
    Poll = Qt.UserRole + 15  # dict или None
    Sticker = Qt.UserRole + 16  # dict или None
    IsPinned = Qt.UserRole + 17  # bool
    ItemType = Qt.UserRole + 18  # str: "message", "date_separator", "unread_separator"
    SeparatorText = Qt.UserRole + 19  # str: текст разделителя
    ShowAuthor = Qt.UserRole + 20  # bool: показывать автора (группировка)
    ShowAvatar = Qt.UserRole + 21  # bool: показывать аватар


class MessageModel(QAbstractListModel):
    """
    Модель данных для списка сообщений.

    Хранит сообщения + разделители дат + метку непрочитанных.
    Автоматически группирует сообщения от одного автора.
    """

    messages_loaded = pyqtSignal()
    message_added = pyqtSignal(str)  # message_id

    def __init__(self, current_user_id: str = "", parent=None):
        super().__init__(parent)
        self._items: list[dict] = []  # Все элементы (сообщения + разделители)
        self._message_index: dict[str, int] = {}  # message_id -> index в _items
        self._current_user_id = current_user_id
        self._last_read_message_id: Optional[str] = None
        self._unread_separator_inserted = False

        # Группировка: сообщения от одного автора в течение 5 минут
        self._grouping_seconds = 300

    def set_current_user(self, user_id: str) -> None:
        """Устанавливает ID текущего пользователя."""
        self._current_user_id = user_id

    def set_last_read_message_id(self, message_id: Optional[str]) -> None:
        """Устанавливает ID последнего прочитанного сообщения."""
        self._last_read_message_id = message_id

    # ========================
    # QAbstractListModel interface
    # ========================

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._items)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid() or index.row() >= len(self._items):
            return None

        item = self._items[index.row()]
        item_type = item.get("__item_type", "message")

        if role == MessageRole.ItemType:
            return item_type

        if item_type in ("date_separator", "unread_separator"):
            if role == MessageRole.SeparatorText:
                return item.get("__separator_text", "")
            return None

        # Роли для сообщений
        role_map = {
            MessageRole.MessageData: lambda: item,
            MessageRole.MessageId: lambda: item.get("id", ""),
            MessageRole.ChatId: lambda: item.get("chat_id", ""),
            MessageRole.AuthorData: lambda: item.get("author", {}),
            MessageRole.Content: lambda: item.get("content", ""),
            MessageRole.MessageType: lambda: item.get("message_type", "text"),
            MessageRole.Timestamp: lambda: item.get("created_at", ""),
            MessageRole.IsOwn: lambda: item.get("author", {}).get("id") == self._current_user_id,
            MessageRole.IsEdited: lambda: item.get("is_edited", False),
            MessageRole.IsDeleted: lambda: item.get("is_deleted", False),
            MessageRole.ReplyTo: lambda: item.get("reply_to"),
            MessageRole.ForwardedFrom: lambda: item.get("forwarded_from"),
            MessageRole.Reactions: lambda: item.get("reactions", []),
            MessageRole.FileAttachment: lambda: item.get("file_attachment"),
            MessageRole.Poll: lambda: item.get("poll"),
            MessageRole.Sticker: lambda: item.get("sticker"),
            MessageRole.IsPinned: lambda: item.get("pinned", False),
            MessageRole.ShowAuthor: lambda: item.get("__show_author", True),
            MessageRole.ShowAvatar: lambda: item.get("__show_avatar", True),
        }

        getter = role_map.get(role)
        if getter:
            return getter()

        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.NoItemFlags
        item = self._items[index.row()]
        if item.get("__item_type") in ("date_separator", "unread_separator"):
            return Qt.ItemIsEnabled  # Разделители не кликабельные
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    # ========================
    # Data Management
    # ========================

    def load_messages(self, messages: list[dict]) -> None:
        """
        Загружает начальный набор сообщений (при открытии чата).
        Автоматически вставляет разделители дат и метку непрочитанных.
        """
        self.beginResetModel()
        self._items.clear()
        self._message_index.clear()
        self._unread_separator_inserted = False

        processed = self._process_messages(messages)
        self._items = processed
        self._rebuild_index()

        self.endResetModel()
        self.messages_loaded.emit()

    def prepend_messages(self, messages: list[dict]) -> None:
        """
        Добавляет старые сообщения в начало (при скролле вверх).
        Правильно обрабатывает дубликаты разделителей.
        """
        if not messages:
            return

        processed = self._process_messages(messages)

        # Удаляем дубликат разделителя дат если совпадает с текущим первым элементом
        # Проверяем оба вида разделителей (дата и непрочитанные)
        if self._items and processed:
            last_new = processed[-1]
            first_existing = self._items[0]
            
            both_are_separators = (
                last_new.get("__item_type") in ("date_separator", "unread_separator") and
                first_existing.get("__item_type") in ("date_separator", "unread_separator")
            )
            
            if both_are_separators and last_new.get("__separator_text") == first_existing.get("__separator_text"):
                processed.pop()

        if not processed:
            return

        count = len(processed)
        self.beginInsertRows(QModelIndex(), 0, count - 1)
        self._items = processed + self._items
        self._rebuild_index()
        self.endInsertRows()

    def append_message(self, message: dict) -> None:
        """
        Добавляет новое сообщение в конец.
        Вставляет разделитель даты если нужно.
        """
        items_to_add = []

        # Проверяем нужен ли разделитель даты
        if self._items:
            last_msg = self._find_last_message()
            if last_msg:
                new_date = self._extract_date(message.get("created_at", ""))
                last_date = self._extract_date(last_msg.get("created_at", ""))
                if new_date and last_date and new_date != last_date:
                    sep_text = format_date_separator(message.get("created_at"))
                    items_to_add.append({
                        "__item_type": "date_separator",
                        "__separator_text": sep_text,
                    })

        # Группировка
        self._apply_grouping_to_message(message)
        items_to_add.append(message)

        count = len(items_to_add)
        start = len(self._items)

        self.beginInsertRows(QModelIndex(), start, start + count - 1)
        self._items.extend(items_to_add)
        self._rebuild_index()
        self.endInsertRows()

        self.message_added.emit(message.get("id", ""))

    def update_message(self, message_id: str, updates: dict) -> None:
        """
        Обновляет данные сообщения (редактирование, реакции, etc).
        """
        idx = self._message_index.get(message_id)
        if idx is None:
            return

        item = self._items[idx]
        item.update(updates)

        model_index = self.index(idx)
        self.dataChanged.emit(model_index, model_index)

    def delete_message(self, message_id: str, for_everyone: bool) -> None:
        """
        Удаляет сообщение.
        for_everyone=True: помечаем is_deleted, content=None
        for_everyone=False: полностью убираем из модели
        """
        idx = self._message_index.get(message_id)
        if idx is None:
            return

        if for_everyone:
            self._items[idx]["is_deleted"] = True
            self._items[idx]["content"] = None
            model_index = self.index(idx)
            self.dataChanged.emit(model_index, model_index)
        else:
            self.beginRemoveRows(QModelIndex(), idx, idx)
            self._items.pop(idx)
            self._rebuild_index()
            self.endRemoveRows()

    def update_reactions(self, message_id: str, reactions: list[dict]) -> None:
        """Обновляет реакции сообщения."""
        self.update_message(message_id, {"reactions": reactions})

    def mark_edited(self, message_id: str, new_content: str) -> None:
        """Помечает сообщение как отредактированное."""
        self.update_message(message_id, {
            "content": new_content,
            "is_edited": True,
        })

    def mark_pinned(self, message_id: str, pinned: bool) -> None:
        """Помечает сообщение как закреплённое/откреплённое."""
        self.update_message(message_id, {"pinned": pinned})

    def update_poll(self, message_id: str, poll_data: dict) -> None:
        """Обновляет данные опроса."""
        self.update_message(message_id, {"poll": poll_data})

    def get_message_by_id(self, message_id: str) -> Optional[dict]:
        """Получает сообщение по ID."""
        idx = self._message_index.get(message_id)
        if idx is not None:
            return self._items[idx]
        return None

    def get_message_index(self, message_id: str) -> Optional[int]:
        """Получает индекс сообщения в модели."""
        return self._message_index.get(message_id)

    def get_first_message_id(self) -> Optional[str]:
        """Получает ID первого сообщения (для пагинации)."""
        for item in self._items:
            if item.get("__item_type", "message") == "message":
                return item.get("id")
        return None

    def get_last_message_id(self) -> Optional[str]:
        """Получает ID последнего сообщения."""
        for item in reversed(self._items):
            if item.get("__item_type", "message") == "message":
                return item.get("id")
        return None

    def is_empty(self) -> bool:
        """Проверяет, есть ли сообщения (не считая разделители)."""
        return not any(
            item.get("__item_type", "message") == "message"
            for item in self._items
        )

    def clear_all(self) -> None:
        """Полная очистка модели."""
        self.beginResetModel()
        self._items.clear()
        self._message_index.clear()
        self._unread_separator_inserted = False
        self.endResetModel()

    # ========================
    # Internal Processing
    # ========================

    def _process_messages(self, messages: list[dict]) -> list[dict]:
        """
        Обрабатывает список сообщений:
        1. Вставляет разделители дат
        2. Вставляет метку непрочитанных
        3. Вычисляет группировку (show_author, show_avatar)
        """
        result = []
        prev_date = None
        prev_author_id = None
        prev_time = None

        for msg in messages:
            # Пропускаем удалённые для всех
            if msg.get("is_deleted", False):
                # Оставляем в списке но помечаем
                pass

            # Разделитель даты
            msg_date = self._extract_date(msg.get("created_at", ""))
            if msg_date and msg_date != prev_date:
                sep_text = format_date_separator(msg.get("created_at"))
                result.append({
                    "__item_type": "date_separator",
                    "__separator_text": sep_text,
                })
                prev_date = msg_date
                prev_author_id = None  # Сброс группировки после разделителя

            # Метка непрочитанных
            if (not self._unread_separator_inserted and
                    self._last_read_message_id and
                    msg.get("id") != self._last_read_message_id):
                # Проверяем, было ли предыдущее сообщение = last_read
                if result and any(
                        item.get("id") == self._last_read_message_id
                        for item in result
                        if item.get("__item_type", "message") == "message"
                ):
                    result.append({
                        "__item_type": "unread_separator",
                        "__separator_text": "Непрочитанные сообщения",
                    })
                    self._unread_separator_inserted = True
                    prev_author_id = None

            # Группировка
            self._apply_grouping(msg, prev_author_id, prev_time)

            result.append(msg)

            # Обновляем prev
            author = msg.get("author", {})
            prev_author_id = author.get("id")
            prev_time = msg.get("created_at")

        return result

    def _apply_grouping(
            self,
            msg: dict,
            prev_author_id: Optional[str],
            prev_time: Optional[str],
    ) -> None:
        """
        Вычисляет, нужно ли показывать автора и аватар.

        Правила:
        - Показываем автора если:
          - Это первое сообщение
          - Автор отличается от предыдущего
          - Прошло > 5 минут с предыдущего сообщения
        - Аватар показываем только если показываем автора
        """
        author = msg.get("author", {})
        author_id = author.get("id")
        msg_time = msg.get("created_at")

        show_author = True

        if prev_author_id and author_id == prev_author_id and prev_time and msg_time:
            # Одинаковый автор — проверяем время
            try:
                t1 = datetime.fromisoformat(prev_time.replace("Z", "+00:00"))
                t2 = datetime.fromisoformat(msg_time.replace("Z", "+00:00"))
                diff = abs((t2 - t1).total_seconds())
                if diff < self._grouping_seconds:
                    show_author = False
            except (ValueError, TypeError):
                pass

        msg["__show_author"] = show_author
        msg["__show_avatar"] = show_author
        msg["__item_type"] = "message"

    def _apply_grouping_to_message(self, msg: dict) -> None:
        """Применяет группировку к одному новому сообщению."""
        last_msg = self._find_last_message()

        prev_author_id = None
        prev_time = None

        if last_msg:
            prev_author_id = last_msg.get("author", {}).get("id")
            prev_time = last_msg.get("created_at")

        self._apply_grouping(msg, prev_author_id, prev_time)

    def _find_last_message(self) -> Optional[dict]:
        """Находит последнее сообщение (не разделитель)."""
        for item in reversed(self._items):
            if item.get("__item_type", "message") == "message":
                return item
        return None

    def _extract_date(self, iso_string: str) -> Optional[str]:
        """Извлекает дату (YYYY-MM-DD) из ISO-строки."""
        if not iso_string:
            return None
        try:
            dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
            local_dt = dt.astimezone(tz=None)
            return local_dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            return None

    def _rebuild_index(self) -> None:
        """Пересоздаёт индекс message_id -> position."""
        self._message_index.clear()
        for i, item in enumerate(self._items):
            if item.get("__item_type", "message") == "message":
                msg_id = item.get("id")
                if msg_id:
                    self._message_index[msg_id] = i