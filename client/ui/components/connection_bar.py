"""
Lantern v2 — Connection Status Bar
Панель состояния соединения с анимацией лунных фаз.
Появляется внизу при потере соединения.

Анимация: 🌑🌒🌓🌔🌕🌖🌗🌘🌑 (цикл)
"""

from typing import Optional
from client.themes.fonts import get_font_family

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QGraphicsOpacityEffect
)
from PyQt5.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QSize, pyqtSignal
)
from PyQt5.QtGui import QFont


class ConnectionBar(QWidget):
    """
    Полоса статуса соединения.

    Состояния:
    1. HIDDEN — соединение в порядке, панель скрыта
    2. RECONNECTING — потеря соединения, анимация луны
    3. FAILED — не удалось переподключиться
    """

    MOON_PHASES = ["🌑", "🌒", "🌓", "🌔", "🌕", "🌖", "🌗", "🌘"]

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("connectionBar")
        self.setFixedHeight(0)  # Скрыта по умолчанию
        self.setVisible(False)

        self._moon_index = 0
        self._target_height = 32
        self._is_error = False

        # Timer для анимации луны
        self._moon_timer = QTimer(self)
        self._moon_timer.timeout.connect(self._rotate_moon)
        self._moon_timer.setInterval(250)  # 4 фазы в секунду

        # Timer для анимации высоты
        self._height_animation: Optional[QPropertyAnimation] = None

        self._build_ui()

    def _build_ui(self) -> None:
        """Строит UI панели."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(10)

        # Луна
        self._moon_label = QLabel(self.MOON_PHASES[0])
        self._moon_label.setObjectName("connectionMoon")
        self._moon_label.setFont(QFont(get_font_family("emoji"), 14))
        self._moon_label.setAlignment(Qt.AlignCenter)
        self._moon_label.setFixedWidth(28)
        layout.addWidget(self._moon_label)

        # Текст
        self._text_label = QLabel("Переподключение к серверу...")
        self._text_label.setObjectName("connectionLabel")
        layout.addWidget(self._text_label, 1)

        # Счётчик попыток
        self._attempt_label = QLabel("")
        self._attempt_label.setObjectName("connectionLabel")
        self._attempt_label.setAlignment(Qt.AlignRight)
        layout.addWidget(self._attempt_label)

    def _safe_repolish(self, widget: QWidget) -> None:
        """Безопасно обновляет стиль виджета."""
        _style = widget.style()
        if _style:
            _style.unpolish(widget)
            _style.polish(widget)

    def show_reconnecting(self, attempt: int = 0) -> None:
        """
        Показывает панель в режиме переподключения.

        Args:
            attempt: Номер текущей попытки.
        """
        self._is_error = False
        self.setObjectName("connectionBar")
        self._safe_repolish(self)

        self._text_label.setObjectName("connectionLabel")
        self._text_label.setText("Потеряно соединение с сервером, переподключение...")
        self._safe_repolish(self._text_label)

        if attempt > 0:
            self._attempt_label.setText(f"Попытка {attempt}")
        else:
            self._attempt_label.setText("")

        if not self._moon_timer.isActive():
            self._moon_timer.start()

        self._show_animated()

    def show_error(self, message: str = "Не удалось подключиться") -> None:
        """Показывает панель в режиме ошибки."""
        self._is_error = True
        self._moon_timer.stop()

        self.setObjectName("connectionBarError")
        self._safe_repolish(self)

        self._moon_label.setText("❌")

        self._text_label.setObjectName("connectionErrorLabel")
        self._text_label.setText(message)
        self._safe_repolish(self._text_label)

        self._attempt_label.setText("")

        self._show_animated()

    def hide_bar(self) -> None:
        """Скрывает панель с анимацией."""
        self._moon_timer.stop()
        self._hide_animated()

    def _rotate_moon(self) -> None:
        """Переключает фазу луны."""
        self._moon_index = (self._moon_index + 1) % len(self.MOON_PHASES)
        self._moon_label.setText(self.MOON_PHASES[self._moon_index])

    def _show_animated(self) -> None:
        """Показывает панель с плавной анимацией высоты."""
        if self.isVisible() and self.height() == self._target_height:
            return

        self.setVisible(True)

        if self._height_animation and self._height_animation.state() == QPropertyAnimation.Running:
            self._height_animation.stop()

        self._height_animation = QPropertyAnimation(self, b"maximumHeight")
        self._height_animation.setDuration(300)
        self._height_animation.setStartValue(0)
        self._height_animation.setEndValue(self._target_height)
        self._height_animation.setEasingCurve(QEasingCurve.OutCubic)
        self._height_animation.start()

        # Также анимируем fixedHeight
        self._h2 = QPropertyAnimation(self, b"minimumHeight")
        self._h2.setDuration(300)
        self._h2.setStartValue(0)
        self._h2.setEndValue(self._target_height)
        self._h2.setEasingCurve(QEasingCurve.OutCubic)
        self._h2.start()

    def _hide_animated(self) -> None:
        """Скрывает панель с плавной анимацией."""
        if not self.isVisible():
            return

        if self._height_animation and self._height_animation.state() == QPropertyAnimation.Running:
            self._height_animation.stop()

        self._height_animation = QPropertyAnimation(self, b"maximumHeight")
        self._height_animation.setDuration(200)
        self._height_animation.setStartValue(self._target_height)
        self._height_animation.setEndValue(0)
        self._height_animation.setEasingCurve(QEasingCurve.InCubic)
        self._height_animation.finished.connect(lambda: self.setVisible(False))
        self._height_animation.start()

        self._h2 = QPropertyAnimation(self, b"minimumHeight")
        self._h2.setDuration(200)
        self._h2.setStartValue(self._target_height)
        self._h2.setEndValue(0)
        self._h2.setEasingCurve(QEasingCurve.InCubic)
        self._h2.start()

    def sizeHint(self) -> QSize:
        if self.isVisible():
            return QSize(400, self._target_height)
        return QSize(400, 0)
