"""System tray icon (Phase 12c): a QSystemTrayIcon showing MushTato,
blinking on unseen activity -- modeled on Potato's real
``::potato::flashSystrayIcon`` (a simple two-icon-position blink every
750ms, verified against the actual source
``~/git/potato/potato.vfs/lib/app-potato/windows/winico/potato-
systray.tcl``), not a multi-frame animation. Potato's real context
menu (Restore / Hide Icon / Exit) is replicated minus "Hide Icon" --
Phase 12 checkpoint: the tray icon is always shown whenever the
platform supports one at all, with no separate show/hide toggle.

Icon graphics: the resting icon is the real MushTato artwork
(gui/assets/icon/, via gui/asset_paths.py) -- this replaces the
original Phase 12c placeholder (a plain QPainter-drawn circle+"M",
noted at the time as "swap out generate_resting_icon()/
generate_activity_icon() for real artwork whenever it exists, without
needing to touch any other code"; real artwork now exists, per the
Item 3/icon+splash plan). The activity (blinking) state composites a
small ACTIVITY_COLOR badge onto the same real icon rather than using a
second, different piece of art -- MushTato only has the one character
icon, unlike Potato's own two distinct icon images, so blinking between
"icon" and "icon + a bright dot" is this project's own equivalent of
Potato's two-icon-position blink, and keeps the same visual language
as MainWindow.ACTIVITY_COLOR's tab-activity flash.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, QRectF, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

from .asset_paths import icon_png_path

# Matches MainWindow.ACTIVITY_COLOR -- the tray icon's "something
# happened" state should read as the same visual language as the tab-
# activity flash, not an unrelated color.
ACTIVITY_COLOR = QColor(255, 140, 0)
# Verified against Potato's own real winico implementation
# (flashSystrayIcon's `after 750 ...`), not a guessed value.
BLINK_INTERVAL_MS = 750
ICON_SIZE = 64


def _load_icon_pixmap() -> QPixmap:
    return QPixmap(str(icon_png_path(ICON_SIZE)))


def generate_resting_icon() -> QIcon:
    return QIcon(_load_icon_pixmap())


def generate_activity_icon() -> QIcon:
    pixmap = QPixmap(_load_icon_pixmap())
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(ACTIVITY_COLOR)
    painter.setPen(QColor(255, 255, 255))
    badge_size = ICON_SIZE * 0.4
    painter.drawEllipse(
        QRectF(ICON_SIZE - badge_size, ICON_SIZE - badge_size, badge_size, badge_size)
    )
    painter.end()
    return QIcon(pixmap)


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
