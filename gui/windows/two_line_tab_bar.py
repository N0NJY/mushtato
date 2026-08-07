"""A QTabBar that renders a tab's label as two lines -- a connection
name on top, a smaller "logged in as" line underneath -- instead of
QTabBar's own single-line text rendering.

Confirmed directly before writing this, not assumed: plain
``QTabWidget.setTabText(index, "line1\\nline2")`` does *not* grow a
tab's height for the embedded newline under Qt's Fusion style (this
project's own forced style, see ``gui/theme.py``) -- ``tabSizeHint()``
comes back the exact same height regardless of how many ``\\n``
characters a tab's text contains, so a plain multi-line string would
just get its second line clipped, not wrapped.

Delegates all of a tab's shape/background/border/hover/selected-state
painting to the real style (``QStyle.drawControl(CE_TabBarTabShape,
...)``), the same primitive Qt's own default QTabBar painting uses --
only the *text* is custom-drawn, as two lines instead of one. Reads
``tabTextColor(index)`` for each line's color rather than hardcoding
one, so MainWindow's existing tab-activity-flash/active-tab-highlight
mechanisms (plain ``setTabTextColor()`` calls) keep working completely
unchanged -- this class has no idea those features exist.
"""

from __future__ import annotations

from typing import Tuple

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QFont, QFontMetrics, QPainter, QPalette
from PySide6.QtWidgets import QStyle, QStyleOptionTab, QTabBar

# Points smaller than the tab bar's own font -- Rick's own request
# ("both can be in smaller text than being used now to save making the
# tabs too large"), applied to both lines uniformly rather than mixing
# two different sizes within one tab.
_FONT_SHRINK_POINTS = 2
_MIN_POINT_SIZE = 6
_LINE_SPACING = 2
_VERTICAL_MARGIN = 3


class TwoLineTabBar(QTabBar):
    def _label_font(self) -> QFont:
        font = QFont(self.font())
        font.setPointSize(max(_MIN_POINT_SIZE, font.pointSize() - _FONT_SHRINK_POINTS))
        return font

    def _lines(self, index: int) -> Tuple[str, str]:
        text = self.tabText(index)
        if "\n" not in text:
            return text, ""
        first, _, second = text.partition("\n")
        return first, second

    def tabSizeHint(self, index: int):  # noqa: N802 -- Qt override
        hint = super().tabSizeHint(index)
        _first, second = self._lines(index)
        if second:
            metrics = QFontMetrics(self._label_font())
            hint.setHeight(2 * metrics.height() + _LINE_SPACING + 2 * _VERTICAL_MARGIN)
        return hint

    def paintEvent(self, event) -> None:  # noqa: N802 -- Qt override
        painter = QPainter(self)
        for index in range(self.count()):
            option = QStyleOptionTab()
            self.initStyleOption(option, index)
            # Suppress the style's own single-line text draw -- we draw
            # the label ourselves below, once the tab's real shape/
            # background/border is already painted.
            option.text = ""
            self.style().drawControl(QStyle.ControlElement.CE_TabBarTabShape, option, painter, self)

            first, second = self._lines(index)
            rect = self.tabRect(index)
            color = self.tabTextColor(index)
            if not color.isValid():
                color = option.palette.color(QPalette.ColorRole.WindowText)
            painter.setPen(color)

            if second:
                font = self._label_font()
                metrics = QFontMetrics(font)
                painter.setFont(font)
                top_rect = QRect(rect.x(), rect.y() + _VERTICAL_MARGIN, rect.width(), metrics.height())
                painter.drawText(top_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, first)
                bottom_rect = QRect(
                    rect.x(),
                    top_rect.bottom() + _LINE_SPACING,
                    rect.width(),
                    metrics.height(),
                )
                painter.drawText(
                    bottom_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, second
                )
            else:
                painter.setFont(self.font())
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, first)
