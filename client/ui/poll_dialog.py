"""
Lantern v2 — Poll Creation Dialog
Диалог создания опроса.
"""

from typing import Optional

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QLabel, QCheckBox, QWidget
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt, pyqtSignal


class PollDialog(QDialog):
    """Диалог создания опроса."""

    poll_created = pyqtSignal(str, list, bool, bool)  # question, options, anon, multi

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("📊 Создать опрос")
        self.setMinimumWidth(420)
        self.setModal(True)

        self._option_inputs: list[QLineEdit] = []

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel("📊 Новый опрос")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)

        # Вопрос
        q_label = QLabel("Вопрос")
        q_label.setObjectName("mutedLabel")
        layout.addWidget(q_label)

        self._question_input = QLineEdit()
        self._question_input.setPlaceholderText("О чём спросить?")
        self._question_input.setMaxLength(256)
        layout.addWidget(self._question_input)

        # Варианты
        opt_label = QLabel("Варианты ответа")
        opt_label.setObjectName("mutedLabel")
        layout.addWidget(opt_label)

        self._options_layout = QVBoxLayout()
        self._options_layout.setSpacing(6)
        layout.addLayout(self._options_layout)

        # Добавляем 2 начальных варианта
        self._add_option("Вариант 1")
        self._add_option("Вариант 2")

        # Кнопка добавить
        add_btn = QPushButton("➕ Добавить вариант")
        add_btn.setObjectName("ghostButton")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(lambda: self._add_option(f"Вариант {len(self._option_inputs) + 1}"))
        layout.addWidget(add_btn)

        # Настройки
        self._anonymous_check = QCheckBox("Анонимное голосование")
        layout.addWidget(self._anonymous_check)

        self._multi_check = QCheckBox("Множественный выбор")
        layout.addWidget(self._multi_check)

        # Ошибка
        self._error_label = QLabel("")
        self._error_label.setObjectName("errorLabel")
        self._error_label.setVisible(False)
        layout.addWidget(self._error_label)

        # Кнопки
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Отмена")
        cancel_btn.setObjectName("secondaryButton")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        create_btn = QPushButton("📊 Создать")
        create_btn.setCursor(Qt.PointingHandCursor)
        create_btn.clicked.connect(self._on_create)
        btn_row.addWidget(create_btn)

        layout.addLayout(btn_row)

    def _add_option(self, placeholder: str) -> None:
        if len(self._option_inputs) >= 10:
            return
        inp = QLineEdit()
        inp.setPlaceholderText(placeholder)
        inp.setMaxLength(128)
        self._option_inputs.append(inp)
        self._options_layout.addWidget(inp)

    def _on_create(self) -> None:
        question = self._question_input.text().strip()
        if not question:
            self._error_label.setText("Введите вопрос")
            self._error_label.setVisible(True)
            return

        options = [inp.text().strip() for inp in self._option_inputs if inp.text().strip()]
        if len(options) < 2:
            self._error_label.setText("Нужно минимум 2 варианта ответа")
            self._error_label.setVisible(True)
            return

        self.poll_created.emit(
            question, options,
            self._anonymous_check.isChecked(),
            self._multi_check.isChecked(),
        )
        self.accept()