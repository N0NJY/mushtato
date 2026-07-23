"""Light/dark theme support (Phase 7b).

QPalette, not Qt Style Sheets or a third-party theme library -- no new
dependency, and standard widgets (dialogs, address book list, buttons,
input boxes, and the scrollback QTextEdit) all pull their colors from
the application-wide palette by default, since nothing in this
codebase has ever set an explicit stylesheet or palette override.
Applying a palette at the QApplication level therefore reaches
everything, chrome and session windows alike, without per-widget work.

The scrollback and input-box colors for the dark theme are Rick's own
real Potato client's actual shipped defaults (from potato.vfs's
lib/potato-config.tcl), not invented values -- Potato's output pane is
black (#000000) with dimmed foreground text (#aeaeae), while its input
box is brighter (white on black) so a user's own typed text stands out
against MUD output. Chrome colors (dialogs/buttons/lists) don't have an
authentic Potato reference -- Potato's own "skin" theming is about
native ttk widget styles (xpnative/aqua), not a custom dark scheme for
its own dialogs -- so those are this project's own reasonable dark
palette, not a copy of anything.

Known, deliberately out-of-scope limitation (checkpoint discussion):
engine/ansi's 16-color ANSI palette is unchanged (still assumes a dark
background, per its Phase 3 xterm-standard values) -- a MUD server
that explicitly sends light/white ANSI foreground colors could still
be hard to read against the light theme's background. A full
theme-aware ANSI remap was considered and explicitly deferred as
bigger scope than this phase.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory

LIGHT = "light"
DARK = "dark"

# Potato's actual defaults (potato.vfs/lib/potato-config.tcl):
#   world(0,top,bg)    #000000  -- output pane background
#   world(0,ansi,fg)   #aeaeae  -- output pane default/unstyled text
#   world(0,bottom,bg) #000000  -- input box background
#   world(0,bottom,fg) #ffffff  -- input box text (brighter than output)
DARK_SCROLLBACK_BASE = "#000000"
DARK_SCROLLBACK_TEXT = "#aeaeae"
DARK_INPUT_BASE = "#000000"
DARK_INPUT_TEXT = "#ffffff"

# No authentic Potato reference for a light theme (Potato's own
# defaults are black-background); this project's own reasonable choice.
LIGHT_SCROLLBACK_BASE = "#ffffff"
LIGHT_SCROLLBACK_TEXT = "#202020"
LIGHT_INPUT_BASE = "#ffffff"
LIGHT_INPUT_TEXT = "#000000"


def build_app_palette(theme: str) -> QPalette:
    """The application-wide palette: dialogs, address book list,
    buttons, and (via inheritance) input boxes.
    """
    palette = QPalette()
    if theme == DARK:
        window = QColor("#2b2b2b")
        window_text = QColor("#d4d4d4")
        base = QColor(DARK_INPUT_BASE)
        text = QColor(DARK_INPUT_TEXT)
        button = QColor("#3c3c3c")
        highlight = QColor("#3a6ea5")
    else:
        window = QColor("#f0f0f0")
        window_text = QColor("#202020")
        base = QColor(LIGHT_INPUT_BASE)
        text = QColor(LIGHT_INPUT_TEXT)
        button = QColor("#e0e0e0")
        highlight = QColor("#3a6ea5")

    palette.setColor(QPalette.ColorRole.Window, window)
    palette.setColor(QPalette.ColorRole.WindowText, window_text)
    palette.setColor(QPalette.ColorRole.Base, base)
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Button, button)
    palette.setColor(QPalette.ColorRole.ButtonText, window_text)
    palette.setColor(QPalette.ColorRole.Highlight, highlight)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    return palette


def apply_theme(app: QApplication, theme: str) -> None:
    """Apply ``theme`` app-wide. Safe to call again later (e.g. after
    the settings dialog saves a change) to attempt a live update --
    see gui/windows/main_window.py and CLAUDE.md for how much of that
    actually reaches already-open windows.

    Forces the Fusion style before setting the palette. On several
    real Linux desktops (KDE/qt6ct-style platform theme integration in
    particular), a native style pulls its own palette from the system
    theme and can silently override an app's own QApplication palette
    for individual widgets -- Fusion is the one built-in Qt style that
    reliably honors an explicitly-set palette everywhere, which is why
    a real-desktop test showed correct dark chrome but a scrollback
    pane that stayed on the system's own light colors instead of this
    module's explicit dark override, despite headless tests and
    offscreen-platform screenshots showing the right colors (the
    offscreen QPA platform doesn't load a real platform theme plugin,
    so it never reproduced this). ``setStyle()`` must come before
    ``setPalette()`` here -- Qt resets to the new style's own default
    palette when the style changes, so setting the palette first would
    just get overwritten.
    """
    app.setStyle(QStyleFactory.create("Fusion"))
    app.setPalette(build_app_palette(theme))


def scrollback_palette(theme: str, base_palette: QPalette) -> QPalette:
    """The scrollback's own palette override: same base app palette,
    but with Base/Text set to the (dimmer, for dark) output-pane colors
    rather than the input-box colors the app-wide palette otherwise
    provides. Matches Potato's real distinction between its brighter
    input box and dimmer output pane.
    """
    palette = QPalette(base_palette)
    if theme == DARK:
        palette.setColor(QPalette.ColorRole.Base, QColor(DARK_SCROLLBACK_BASE))
        palette.setColor(QPalette.ColorRole.Text, QColor(DARK_SCROLLBACK_TEXT))
    else:
        palette.setColor(QPalette.ColorRole.Base, QColor(LIGHT_SCROLLBACK_BASE))
        palette.setColor(QPalette.ColorRole.Text, QColor(LIGHT_SCROLLBACK_TEXT))
    return palette


def apply_widget_and_viewport_palette(scroll_area, palette: QPalette) -> None:
    """Apply ``palette`` to a QAbstractScrollArea (e.g. QTextEdit/
    QTextBrowser) *and its viewport*.

    Found via real-desktop pixel sampling (not assumed): this class of
    widget's visible background is actually painted by a separate
    child widget, ``viewport()`` -- calling ``.setPalette()`` on the
    outer widget alone was leaving the viewport on its default (white)
    background regardless of theme, even though the palette object
    itself was correct. Setting the palette (and forcing
    ``autoFillBackground``) on both the widget and its viewport is the
    standard fix for this well-known Qt gotcha. Any scroll-area-based
    pane in this codebase should go through this rather than a bare
    ``.setPalette()`` call.
    """
    scroll_area.setPalette(palette)
    scroll_area.setAutoFillBackground(True)
    scroll_area.viewport().setPalette(palette)
    scroll_area.viewport().setAutoFillBackground(True)


def apply_scrollback_theme(text_edit, theme: str) -> None:
    """Apply the *scrollback-specific* (dimmed output-pane) palette to
    a QTextEdit and its viewport -- see
    ``apply_widget_and_viewport_palette`` for why both need it. Use
    this for actual MUD-output scrollback panes; for a widget that
    should just follow the regular app-wide/chrome palette instead
    (e.g. the Help window's reference-document pane, which isn't MUD
    output and has no reason to use Potato's dimmed output colors),
    call ``apply_widget_and_viewport_palette`` directly with the
    widget's own inherited palette instead.
    """
    palette = scrollback_palette(theme, text_edit.palette())
    apply_widget_and_viewport_palette(text_edit, palette)
