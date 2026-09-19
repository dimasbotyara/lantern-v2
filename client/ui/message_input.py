"""
Lantern v2 — Message Input Widget
Многострочное поле ввода с автоматическим расширением.

Фичи:
- Авторасширение до 8 строк, потом скролл
- Счётчик символов (4096 макс)
- Enter = отправить, Shift+Enter = новая строка
- Превью ответа (reply bar)
- Кнопки: прикрепить файл, эмодзи, стикеры, отправить
- Индикатор typing (debounce 1 сек)
- Предложение "отправить как .txt" при превышении лимита
"""

import asyncio
from typing import Optional
from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QPushButton, QLabel, QFileDialog, QSizePolicy,
    QMessageBox, QApplication
)
from PyQt5.QtGui import (
    QFont, QTextCursor, QKeyEvent, QFontMetrics,
    QColor, QTextCharFormat
)
from PyQt5.QtCore import (
    Qt, QSize, pyqtSignal, QTimer, QPropertyAnimation,
    QEasingCurve
)

from client.ui.components.reply_preview import ReplyPreviewBar
from client.ui.components.emoji_picker import EmojiPicker
from client.themes.catppuccin import Palette, AccentColor


class MessageInput(QWidget):
    """
    Виджет ввода сообщения.

    Layout:
    ┌──────────────────────────────────────────────┐
    │ [Reply Preview Bar]                      [✕] │  ← Показывается при ответе
    ├──────────────────────────────────────────────┤
    │ [📎] [Многострочное поле ввода...] [😊] [➤] │
    │                                  4096/4096   │  ← Счётчик при приближении к лимиту
    └──────────────────────────────────────────────┘
    """

    # Сигналы
    message_submitted = pyqtSignal(str, str)  # content, reply_to_id (or "")
    file_attach_requested = pyqtSignal()  # Открыть диалог выбора файла
    file_upload_requested = pyqtSignal(str, str)
    typing_started = pyqtSignal()  # Пользователь печатает
    emoji_picker_requested = pyqtSignal(object)  # QPoint position
    sticker_picker_requested = pyqtSignal(object)  # QPoint position
    poll_create_requested = pyqtSignal()  # Создать опрос
    edit_submitted = pyqtSignal(str, str)  # message_id, new_content

    MAX_CHARS = 4096
    MIN_HEIGHT = 48
    MAX_HEIGHT = 220
    SINGLE_LINE_HEIGHT = 48

    def __init__(
            self,
            palette: Palette,
            accent: AccentColor,
            parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setObjectName("messageInputArea")

        self._palette = palette
        self._accent = accent
        self._reply_message_id: Optional[str] = None
        self._edit_message_id: Optional[str] = None
        self._edit_original_content: Optional[str] = None
        self._typing_timer = QTimer(self)
        self._typing_timer.setSingleShot(True)
        self._typing_timer.setInterval(1000)

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Строит UI."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 6, 12, 8)
        main_layout.setSpacing(4)

        # === Reply Preview ===
        self._reply_bar = ReplyPreviewBar()
        self._reply_bar.close_requested.connect(self.cancel_reply)
        main_layout.addWidget(self._reply_bar)

        # === Edit indicator ===
        self._edit_bar = QWidget()
        self._edit_bar.setObjectName("replyPreviewBar")
        self._edit_bar.setVisible(False)
        edit_bar_layout = QHBoxLayout(self._edit_bar)
        edit_bar_layout.setContentsMargins(0, 0, 0, 0)
        edit_bar_layout.setSpacing(8)

        self._edit_label = QLabel("✏️ Редактирование")
        self._edit_label.setObjectName("replyPreviewAuthor")
        edit_bar_layout.addWidget(self._edit_label, 1)

        edit_close_btn = QPushButton("✕")
        edit_close_btn.setObjectName("replyCloseButton")
        edit_close_btn.setCursor(Qt.PointingHandCursor)
        edit_close_btn.clicked.connect(self.cancel_edit)
        edit_bar_layout.addWidget(edit_close_btn)

        main_layout.addWidget(self._edit_bar)

        # === Input Row ===
        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.setSpacing(6)

        # Кнопка прикрепить файл
        self._attach_btn = QPushButton("📎")
        self._attach_btn.setObjectName("iconButton")
        self._attach_btn.setCursor(Qt.PointingHandCursor)
        self._attach_btn.setToolTip("Прикрепить файл")
        self._attach_btn.setFont(QFont("Segoe UI Emoji", 16))
        self._attach_btn.setFixedSize(40, 40)
        input_row.addWidget(self._attach_btn)

        # Текстовое поле
        self._text_edit = _AutoResizeTextEdit(self._palette, self._accent)
        self._text_edit.setObjectName("messageInput")
        self._text_edit.setPlaceholderText("Написать сообщение...")
        self._text_edit.setFont(QFont("Segoe UI", 14))
        self._text_edit.setFixedHeight(self.SINGLE_LINE_HEIGHT)
        self._text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # Подключаем события текстового поля
        self._text_edit.submit_requested.connect(self._on_submit)
        self._text_edit.text_changed_signal.connect(self._on_text_changed)
        self._text_edit.height_changed.connect(self._on_height_changed)

        input_row.addWidget(self._text_edit, 1)

        # Кнопки справа
        right_buttons = QVBoxLayout()
        right_buttons.setSpacing(2)
        right_buttons.setContentsMargins(0, 0, 0, 0)

        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(2)

        # Эмодзи
        self._emoji_btn = QPushButton("😊")
        self._emoji_btn.setObjectName("iconButton")
        self._emoji_btn.setCursor(Qt.PointingHandCursor)
        self._emoji_btn.setToolTip("Эмодзи")
        self._emoji_btn.setFont(QFont("Segoe UI Emoji", 16))
        self._emoji_btn.setFixedSize(36, 36)
        buttons_row.addWidget(self._emoji_btn)

        # Отправить
        self._send_btn = QPushButton("➤")
        self._send_btn.setObjectName("sendButton")
        self._send_btn.setCursor(Qt.PointingHandCursor)
        self._send_btn.setToolTip("Отправить (Enter)")
        self._send_btn.setFont(QFont("Segoe UI", 16))
        self._send_btn.setEnabled(False)
        buttons_row.addWidget(self._send_btn)

        right_buttons.addLayout(buttons_row)
        input_row.addLayout(right_buttons)

        main_layout.addLayout(input_row)

        # === Char counter (скрыт по умолчанию) ===
        self._char_counter = QLabel("")
        self._char_counter.setObjectName("charCounter")
        self._char_counter.setAlignment(Qt.AlignRight)
        self._char_counter.setVisible(False)
        main_layout.addWidget(self._char_counter)

    def _connect_signals(self) -> None:
        """Подключает сигналы."""
        self._attach_btn.clicked.connect(self._on_attach_clicked)
        self._emoji_btn.clicked.connect(self._on_emoji_clicked)
        self._send_btn.clicked.connect(self._on_submit)

    # ========================
    # Public API
    # ========================

    def set_reply(
            self,
            message_id: str,
            author_name: str,
            author_color: str,
            content: str,
            message_type: str = "text",
    ) -> None:
        """Устанавливает режим ответа."""
        self.cancel_edit()  # Отменяем редактирование если было

        self._reply_message_id = message_id
        self._reply_bar.set_reply(
            message_id, author_name, author_color, content, message_type,
        )
        self._text_edit.setFocus()

    def cancel_reply(self) -> None:
        """Отменяет режим ответа."""
        self._reply_message_id = None
        self._reply_bar.clear()

    def set_edit(self, message_id: str, current_content: str) -> None:
        """Устанавливает режим редактирования."""
        self.cancel_reply()  # Отменяем ответ если был

        self._edit_message_id = message_id
        self._edit_original_content = current_content
        self._edit_bar.setVisible(True)
        self._text_edit.setPlainText(current_content)
        self._text_edit.moveCursor(QTextCursor.End)
        self._text_edit.setFocus()

        # Меняем кнопку отправки
        self._send_btn.setText("✓")
        self._send_btn.setToolTip("Сохранить (Enter)")
        self._send_btn.setEnabled(True)

    def cancel_edit(self) -> None:
        """Отменяет режим редактирования."""
        if self._edit_message_id:
            self._edit_message_id = None
            self._edit_original_content = None
            self._edit_bar.setVisible(False)
            self._text_edit.clear()
            self._send_btn.setText("➤")
            self._send_btn.setToolTip("Отправить (Enter)")
            self._send_btn.setEnabled(False)

    def insert_emoji(self, emoji: str) -> None:
        """Вставляет эмодзи в текущую позицию курсора."""
        self._text_edit.insertPlainText(emoji)
        self._text_edit.setFocus()

    def set_theme(self, palette: Palette, accent: AccentColor) -> None:
        """Обновляет тему."""
        self._palette = palette
        self._accent = accent
        self._text_edit.set_theme(palette, accent)

    def clear_input(self) -> None:
        """Очищает поле ввода."""
        self._text_edit.clear()
        self.cancel_reply()
        self.cancel_edit()

    def set_focus(self) -> None:
        """Устанавливает фокус на поле ввода."""
        self._text_edit.setFocus()

    @property
    def is_editing(self) -> bool:
        return self._edit_message_id is not None

    @property
    def is_replying(self) -> bool:
        return self._reply_message_id is not None

    # ========================
    # Event Handlers
    # ========================

    def _on_submit(self) -> None:
        """Обработка отправки/сохранения."""
        text = self._text_edit.toPlainText().strip()

        if not text:
            return

        if len(text) > self.MAX_CHARS:
            self._show_too_long_dialog(text)
            return

        if self._edit_message_id:
            # Режим редактирования
            if text != self._edit_original_content:
                self.edit_submitted.emit(self._edit_message_id, text)
            self.cancel_edit()
        else:
            # Обычная отправка
            reply_id = self._reply_message_id or ""
            self.message_submitted.emit(text, reply_id)
            self._text_edit.clear()
            self.cancel_reply()

    def _on_text_changed(self) -> None:
        """Обработка изменения текста."""
        text = self._text_edit.toPlainText()
        length = len(text)

        # Кнопка отправки
        has_text = length > 0
        if not self._edit_message_id:
            self._send_btn.setEnabled(has_text)

        # Счётчик символов
        if length > self.MAX_CHARS * 0.8:  # > 80%
            remaining = self.MAX_CHARS - length
            self._char_counter.setText(f"{length}/{self.MAX_CHARS}")
            self._char_counter.setVisible(True)

            if length > self.MAX_CHARS:
                self._char_counter.setObjectName("charCounterError")
            elif length > self.MAX_CHARS * 0.95:
                self._char_counter.setObjectName("charCounterWarning")
            else:
                self._char_counter.setObjectName("charCounter")

            self._char_counter.style().unpolish(self._char_counter)
            self._char_counter.style().polish(self._char_counter)
        else:
            self._char_counter.setVisible(False)

        # Typing indicator (debounce)
        if has_text and not self._typing_timer.isActive():
            self.typing_started.emit()
        self._typing_timer.start()

    def _on_height_changed(self, new_height: int) -> None:
        """Обработка изменения высоты текстового поля."""
        # Ограничиваем высоту
        clamped = max(self.SINGLE_LINE_HEIGHT, min(new_height, self.MAX_HEIGHT))
        self._text_edit.setFixedHeight(clamped)

    def _on_attach_clicked(self) -> None:
        """Открывает диалог выбора файла."""
        self.file_attach_requested.emit()

    def _on_emoji_clicked(self) -> None:
        """Показывает пикер эмодзи."""
        pos = self._emoji_btn.mapToGlobal(
            self._emoji_btn.rect().topLeft()
        )
        pos.setY(pos.y() - 430)
        pos.setX(pos.x() - 340)
        self.emoji_picker_requested.emit(pos)

    def _show_too_long_dialog(self, text: str) -> None:
        """
        Предлагает варианты при превышении лимита.
        Использует неблокирующий .open() вместо .exec_().
        """
        msg = QMessageBox(self)
        msg.setWindowTitle("Сообщение слишком длинное")
        msg.setText(
            f"Сообщение содержит {len(text)} символов "
            f"(максимум {self.MAX_CHARS}).\n\n"
            "Что вы хотите сделать?"
        )

        send_txt_btn = msg.addButton("📄 Отправить как .txt", QMessageBox.AcceptRole)
        split_btn = msg.addButton("✂️ Разделить", QMessageBox.ActionRole)
        cancel_btn = msg.addButton("Отмена", QMessageBox.RejectRole)

        def on_finished(result: int) -> None:
            clicked = msg.clickedButton()
            if clicked == send_txt_btn:
                self._send_as_txt(text)
            elif clicked == split_btn:
                self._split_and_send(text)
            msg.deleteLater()

        msg.finished.connect(on_finished)
        msg.open()

    def _send_as_txt(self, text: str) -> None:
        """
        Отправляет длинный текст как .txt файл.

        Сохраняет текст во временный файл и эмитит сигнал
        file_upload_requested — MainWindow сам загрузит его
        через file_transfer_manager, как обычное вложение.
        """
        import tempfile
        from datetime import datetime

        # Формируем красивое имя файла
        timestamp = datetime.now().strftime("%Y-%m-%d %H-%M-%S")
        filename = f"Сообщение от {timestamp}.txt"

        # Создаём временный файл в системной tmp-директории
        tmp_dir = Path(tempfile.gettempdir()) / "lantern_v2"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = tmp_dir / filename

        try:
            tmp_path.write_text(text, encoding="utf-8")
        except OSError as e:
            QMessageBox.warning(
                self,
                "Ошибка",
                f"Не удалось сохранить файл:\n{e}",
            )
            return

        # Запоминаем reply_id — если пользователь отвечал на кого-то,
        # .txt тоже уйдёт как ответ
        reply_id = self._reply_message_id or ""

        # Эмитим сигнал — MainWindow подхватит
        self.file_upload_requested.emit(str(tmp_path), reply_id)

        # Очищаем поле ввода и сбрасываем reply
        self._text_edit.clear()
        self.cancel_reply()

    def _split_and_send(self, text: str) -> None:
        """
        Разделяет длинное сообщение на части и отправляет их
        последовательно с небольшой задержкой между отправками.
        """
        chunks = []
        while text:
            if len(text) <= self.MAX_CHARS:
                chunks.append(text)
                break

            split_pos = self.MAX_CHARS
            # Пробуем разбить по переносу строки
            newline_pos = text.rfind('\n', 0, split_pos)
            if newline_pos > split_pos * 0.5:
                split_pos = newline_pos + 1
            else:
                space_pos = text.rfind(' ', 0, split_pos)
                if space_pos > split_pos * 0.5:
                    split_pos = space_pos + 1

            chunks.append(text[:split_pos])
            text = text[split_pos:]

        reply_id = self._reply_message_id or ""

        # Отправляем первую часть с reply, остальные — без,
        # с небольшой задержкой чтобы порядок сохранился
        if chunks:
            self.message_submitted.emit(chunks[0], reply_id)

        for i, chunk in enumerate(chunks[1:], start=1):
            # QTimer.singleShot(i * 100, ...) — отправить через i*100 мс
            QTimer.singleShot(
                i * 100,
                lambda c=chunk: self.message_submitted.emit(c, ""),
            )

        self._text_edit.clear()
        self.cancel_reply()


class _AutoResizeTextEdit(QTextEdit):
    """
    QTextEdit с автоматическим изменением высоты.

    - Растёт при добавлении строк (до MAX_HEIGHT)
    - Enter = отправить, Shift+Enter = новая строка
    - Правильный sizeHint
    """

    submit_requested = pyqtSignal()
    text_changed_signal = pyqtSignal()
    height_changed = pyqtSignal(int)

    MIN_H = 48
    MAX_H = 220
    LINE_PADDING = 20  # Padding внутри текстового поля

    def __init__(self, palette: Palette, accent: AccentColor, parent=None):
        super().__init__(parent)
        self._palette = palette
        self._accent = accent
        self._enter_sends = True

        self.setAcceptRichText(False)
        self.setTabChangesFocus(False)
        self.document().setDocumentMargin(4)

        self.textChanged.connect(self._on_text_changed)

    def set_theme(self, palette: Palette, accent: AccentColor) -> None:
        self._palette = palette
        self._accent = accent

    def set_enter_sends(self, enabled: bool) -> None:
        """Устанавливает поведение Enter."""
        self._enter_sends = enabled

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Обработка клавиш."""
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self._enter_sends and not event.modifiers() & Qt.ShiftModifier:
                # Enter = отправить
                self.submit_requested.emit()
                return
            elif not self._enter_sends and event.modifiers() & Qt.ShiftModifier:
                # Shift+Enter = отправить (альтернативный режим)
                self.submit_requested.emit()
                return
            # Иначе — новая строка (стандартное поведение)

        super().keyPressEvent(event)

    def _on_text_changed(self) -> None:
        """Пересчитывает высоту при изменении текста."""
        self.text_changed_signal.emit()

        # Вычисляем нужную высоту
        doc = self.document()
        doc_height = int(doc.size().height())
        needed_height = doc_height + self.LINE_PADDING

        # Ограничиваем
        clamped = max(self.MIN_H, min(needed_height, self.MAX_H))

        if clamped != self.height():
            self.height_changed.emit(clamped)

    def sizeHint(self) -> QSize:
        return QSize(300, self.MIN_H)

    def minimumSizeHint(self) -> QSize:
        return QSize(100, self.MIN_H)
