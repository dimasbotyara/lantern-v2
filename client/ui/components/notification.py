"""
Lantern v2 — Notification System
Внутренние toast-уведомления + системные уведомления (Windows/Linux).
"""

import sys
import asyncio
from typing import Optional

from PyQt5.QtWidgets import (
    QWidget, QLabel, QHBoxLayout, QVBoxLayout,
    QGraphicsOpacityEffect, QApplication
)
from PyQt5.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve,
    QPoint, QRect, QSize
)
from PyQt5.QtGui import QFont


class ToastNotification(QWidget):
    """
    Внутреннее toast-уведомление.
    Плавно появляется сверху справа и исчезает через 4 секунды.
    """

    # Стек активных уведомлений для позиционирования
    _active_toasts: list["ToastNotification"] = []

    def __init__(
            self,
            title: str,
            body: str,
            emoji: str = "💬",
            duration_ms: int = 4000,
            parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setObjectName("notificationToast")
        self.setWindowFlags(
            Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        self._duration = duration_ms
        self._build_ui(title, body, emoji)

        # Анимация прозрачности
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)
        self._opacity_effect.setOpacity(0.0)

        self.setFixedWidth(340)
        self.adjustSize()

    def _build_ui(self, title: str, body: str, emoji: str) -> None:
        """Строит UI уведомления."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # Эмодзи
        emoji_label = QLabel(emoji)
        emoji_label.setFont(QFont("Segoe UI Emoji", 24))
        emoji_label.setAlignment(Qt.AlignTop)
        emoji_label.setFixedWidth(36)
        layout.addWidget(emoji_label)

        # Текст
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)

        title_label = QLabel(title)
        title_label.setObjectName("notificationTitle")
        title_label.setWordWrap(True)
        text_layout.addWidget(title_label)

        if body:
            body_label = QLabel(body)
            body_label.setObjectName("notificationBody")
            body_label.setWordWrap(True)
            # Обрезаем длинный текст
            if len(body) > 100:
                body_label.setText(body[:100] + "...")
            text_layout.addWidget(body_label)

        layout.addLayout(text_layout, 1)

    def show_animated(self) -> None:
        """Показывает уведомление с анимацией."""
        # Позиционирование
        screen = QApplication.primaryScreen()
        if screen:
            screen_rect = screen.availableGeometry()
        else:
            screen_rect = QRect(0, 0, 1920, 1080)

        # Вычисляем позицию (справа сверху, стек)
        x = screen_rect.right() - self.width() - 20
        y_offset = 20
        for toast in ToastNotification._active_toasts:
            if toast.isVisible():
                y_offset += toast.height() + 8

        y = screen_rect.top() + y_offset
        self.move(x, y)

        ToastNotification._active_toasts.append(self)

        self.show()

        # Fade in
        self._fade_in = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_in.setDuration(200)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_in.start()

        # Таймер автоскрытия
        QTimer.singleShot(self._duration, self._fade_out)

    def _fade_out(self) -> None:
        """Скрывает с анимацией."""
        self._fade_animation = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_animation.setDuration(300)
        self._fade_animation.setStartValue(1.0)
        self._fade_animation.setEndValue(0.0)
        self._fade_animation.setEasingCurve(QEasingCurve.InCubic)
        self._fade_animation.finished.connect(self._on_hidden)
        self._fade_animation.start()

    def _on_hidden(self) -> None:
        """Очистка после скрытия."""
        if self in ToastNotification._active_toasts:
            ToastNotification._active_toasts.remove(self)
        self.close()
        self.deleteLater()

    def mousePressEvent(self, event) -> None:
        """Клик по уведомлению — закрывает его."""
        self._fade_out()


def send_system_notification(title: str, body: str, app_name: str = "Lantern v2") -> None:
    """
    Отправляет системное уведомление.
    Поддержка: Windows (toast), Linux (freedesktop/KDE).

    Args:
        title: Заголовок уведомления.
        body: Текст уведомления.
        app_name: Имя приложения.
    """
    try:
        from plyer import notification as plyer_notification
        plyer_notification.notify(
            title=title,
            message=body,
            app_name=app_name,
            timeout=5,
        )
    except ImportError:
        # plyer не установлен — используем fallback
        _fallback_notification(title, body)
    except Exception as e:
        print(f"[Notification] System notification error: {e}")


def _fallback_notification(title: str, body: str) -> None:
    """Fallback для системных уведомлений."""
    if sys.platform == "win32":
        try:
            # Windows 10+ toast через PowerShell
            import subprocess
            script = f'''
            [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
            $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
            $textNodes = $template.GetElementsByTagName("text")
            $textNodes.Item(0).AppendChild($template.CreateTextNode("{title}")) | Out-Null
            $textNodes.Item(1).AppendChild($template.CreateTextNode("{body}")) | Out-Null
            $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
            [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Lantern v2").Show($toast)
            '''
            subprocess.Popen(
                ["powershell", "-Command", script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except Exception:
            pass

    elif sys.platform == "linux":
        try:
            import subprocess
            subprocess.Popen(
                ["notify-send", "--app-name=Lantern v2", title, body],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            pass