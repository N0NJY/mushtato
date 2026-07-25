"""System tray icon (Phase 12c): a QSystemTrayIcon showing MushTato,
blinking on unseen activity -- modeled on Potato's real
``::potato::flashSystrayIcon`` (a simple two-icon-position blink every
750ms, verified against the actual source
``~/git/potato/potato.vfs/lib/app-potato/windows/winico/potato-
systray.tcl``), not a multi-frame animation. Potato's real context
menu (Restore / Hide Icon / Exit) is replicated minus "Hide Icon" --
Phase 12 checkpoint: the tray icon is always shown whenever the
platform supports one at all, with no separate show/hide toggle.

Icon graphics are simple, programmatically-generated placeholders
(``QPainter``/``QPixmap`` -- no new dependency; Pillow isn't part of
this project's tech stack) rather than real branding, per the same
checkpoint -- swap out ``generate_resting_icon()``/
``generate_activity_icon()`` for real artwork whenever it exists,
without needing to touch any other code.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

# A muted, clearly-a-placeholder color -- not real branding.
RESTING_COLOR = QColor(140, 90, 60)
# Matches MainWindow.ACTIVITY_COLOR -- the tray icon's "something
# happened" state should read as the same visual language as the tab-
# activity flash, not an unrelated color.
ACTIVITY_COLOR = QColor(255, 140, 0)
# Verified against Potato's own real winico implementation
# (flashSystrayIcon's `after 750 ...`), not a guessed value.
BLINK_INTERVAL_MS = 750
ICON_SIZE = 64


def _generate_icon(color: QColor) -> QIcon:
    pixmap = QPixmap(ICON_SIZE, ICON_SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(color)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(2, 2, ICON_SIZE - 4, ICON_SIZE - 4)
    painter.setPen(QColor(255, 255, 255))
    font = QFont()
    font.setBold(True)
    font.setPointSize(int(ICON_SIZE * 0.45))
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "M")
    painter.end()
    return QIcon(pixmap)


def generate_resting_icon() -> QIcon:
    return _generate_icon(RESTING_COLOR)


def generate_activity_icon() -> QIcon:
    return _generate_icon(ACTIVITY_COLOR)


class TrayIcon(QObject):
    """Owns the actual QSystemTrayIcon, its context menu, and the
    blink timer. Decoupled from MainWindow via plain signals
    (``restore_requested``/``exit_requested``) rather than holding a
    direct reference to it, matching the same reasoning MailWindow's
    ``send_line``/``persist_world`` callables already established --
    independently constructible and testable without a real MainWindow.
    """

    restore_requested = Signal()
    exit_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._resting_icon = generate_resting_icon()
        self._activity_icon = generate_activity_icon()
        self._blink_on = False

        self.tray = QSystemTrayIcon(self._resting_icon, self)
        self.tray.setToolTip("MushTato")
        self.tray.activated.connect(self._on_activated)

        self.menu = QMenu()
        self.restore_action = self.menu.addAction("Restore")
        self.restore_action.triggered.connect(self.restore_requested.emit)
        self.menu.addSeparator()
        self.exit_action = self.menu.addAction("Exit")
        self.exit_action.triggered.connect(self.exit_requested.emit)
        self.tray.setContextMenu(self.menu)

        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(BLINK_INTERVAL_MS)
        self._blink_timer.timeout.connect(self._tick)

    def show(self) -> None:
        self.tray.show()

    def _on_activated(self, reason) -> None:
        # Left-click (Trigger) or double-click restores -- matches
        # Potato's real winicoCallback (WM_LBUTTONUP -> restore).
        # Right-click's context menu is handled automatically by Qt via
        # setContextMenu() above, no explicit handling needed here.
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.restore_requested.emit()

    def start_blinking(self) -> None:
        if self._blink_timer.isActive():
            return
        self._blink_on = True
        self.tray.setIcon(self._activity_icon)
        self._blink_timer.start()

    def stop_blinking(self) -> None:
        self._blink_timer.stop()
        self._blink_on = False
        self.tray.setIcon(self._resting_icon)

    def _tick(self) -> None:
        self._blink_on = not self._blink_on
        self.tray.setIcon(self._activity_icon if self._blink_on else self._resting_icon)
