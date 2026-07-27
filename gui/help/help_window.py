"""The in-app Help window (Phase 8): one scrollable reference document
with a linked table of contents, replacing the Phase 7c /help
placeholder.

Single-document-with-TOC, not a QTabWidget of ~10 tabs or a separate
sidebar-list + content-pane split -- fewer tabs across the top scale
better as sections are added later, and this is also the closest real
parallel to TinyFugue's own actual help system (an indexed text file
read top-to-bottom with jump targets, per the Phase 7c research into
TinyFugue's src/help.c).

Navigation is *not* implemented via Markdown-generated HTML anchors --
verified empirically (not assumed) that Qt's QTextDocument.setMarkdown()
does not assign any id/name to the HTML it generates for "## Heading"
lines, so a TOC link's target never actually exists in the document and
QTextBrowser.scrollToAnchor() silently does nothing. Instead, each
section's starting QTextCursor position is recorded while the combined
document is being assembled, and a TOC link click (caught via
anchorClicked, with setOpenLinks(False) so Qt doesn't try to resolve it
itself) jumps the cursor to that recorded position directly -- this
only relies on documented, guaranteed QTextCursor/QTextBrowser behavior,
not on Qt's Markdown converter doing something it turns out not to do.
"""

from __future__ import annotations

from typing import Dict

from PySide6.QtGui import QAction, QTextBlockFormat, QTextCursor
from PySide6.QtWidgets import QMainWindow, QTextBrowser, QVBoxLayout, QWidget

from ..splash import show_splash_again
from ..theme import apply_widget_and_viewport_palette
from .topics import TOPICS, HelpContext


class HelpWindow(QMainWindow):
    def __init__(self, *, hotkeys: Dict[str, str], theme: str) -> None:
        super().__init__()
        self.setWindowTitle("MushTato — Help")
        self.resize(700, 600)

        self.browser = QTextBrowser(self)
        self.browser.setOpenLinks(False)
        self.browser.anchorClicked.connect(self._on_anchor_clicked)
        self._section_positions: Dict[str, int] = {}

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.addWidget(self.browser)
        self.setCentralWidget(central)

        self._build_menu()
        self.refresh(hotkeys, theme)

    def _build_menu(self) -> None:
        # Rick's own requested "a link to show the [splash] screen"
        # from within Help -- reuses show_splash_again() (gui/splash.py)
        # as-is, not a parallel re-implementation. Kept as a named
        # self.* attribute, not a bare local, per the real PySide6/
        # shiboken wrapper-lifetime bug found in Phase 7d (a QMenu/
        # QAction kept only as a local can have its underlying C++
        # object garbage-collected once this method returns).
        menu_bar = self.menuBar()
        self.view_menu = menu_bar.addMenu("&View")
        self.show_splash_action = QAction("Show Splash Screen", self)
        self.show_splash_action.triggered.connect(lambda: show_splash_again())
        self.view_menu.addAction(self.show_splash_action)

    def refresh(self, hotkeys: Dict[str, str], theme: str) -> None:
        """Rebuild the document from current live data (hotkeys/theme
        can change between opens -- this window is a reused singleton,
        not reconstructed each time, so its content must be refreshed
        explicitly rather than risk showing stale bindings/theme).
        """
        context = HelpContext(hotkeys=dict(hotkeys), theme=theme)
        self.browser.clear()
        self._section_positions = {}

        cursor = QTextCursor(self.browser.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)

        toc_lines = ["# MushTato Help", "", "**Contents**", ""]
        toc_lines += [f"- [{topic.title}](#{topic.slug})" for topic in TOPICS]
        cursor.insertMarkdown("\n".join(toc_lines) + "\n\n")

        for topic in TOPICS:
            cursor.movePosition(QTextCursor.MoveOperation.End)
            # A fresh, explicitly-reset block before each section --
            # found empirically (not assumed) that calling
            # insertMarkdown() again right after a bullet-list block
            # left the cursor still "inside" that list's context, so
            # the next section's "# Heading" got absorbed as text into
            # the previous list item instead of starting a real new
            # heading block.
            cursor.insertBlock(QTextBlockFormat())
            self._section_positions[topic.slug] = cursor.position()
            cursor.insertMarkdown(topic.render(context) + "\n\n")

        # Re-applies the app's own current chrome palette (not the
        # dimmed scrollback-specific one -- this is a reference
        # document, not MUD output) to both the browser and its
        # viewport; see apply_widget_and_viewport_palette's docstring
        # for why both need it.
        apply_widget_and_viewport_palette(self.browser, self.palette())

        self.browser.moveCursor(QTextCursor.MoveOperation.Start)

    def _on_anchor_clicked(self, url) -> None:
        fragment = url.fragment()
        self.jump_to(fragment)

    def jump_to(self, slug: str) -> bool:
        position = self._section_positions.get(slug)
        if position is None:
            return False
        cursor = QTextCursor(self.browser.document())
        cursor.setPosition(position)
        self.browser.setTextCursor(cursor)
        self.browser.ensureCursorVisible()
        return True

    def showEvent(self, event) -> None:  # noqa: N802 -- Qt override signature
        super().showEvent(event)
        apply_widget_and_viewport_palette(self.browser, self.palette())
