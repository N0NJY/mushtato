"""Headless tests for gui/theme.py's palette construction."""

from gui.theme import (
    DARK_INPUT_BASE,
    DARK_INPUT_TEXT,
    DARK_SCROLLBACK_BASE,
    DARK_SCROLLBACK_TEXT,
    LIGHT_SCROLLBACK_BASE,
    LIGHT_SCROLLBACK_TEXT,
    apply_scrollback_theme,
    apply_theme,
    build_app_palette,
    scrollback_palette,
)
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QTextEdit


def test_dark_app_palette_uses_potato_input_colors(qapp):
    palette = build_app_palette("dark")
    assert palette.color(QPalette.ColorRole.Base) == QColor(DARK_INPUT_BASE)
    assert palette.color(QPalette.ColorRole.Text) == QColor(DARK_INPUT_TEXT)


def test_dark_scrollback_palette_uses_potato_output_colors_not_input_colors(qapp):
    app_palette = build_app_palette("dark")
    palette = scrollback_palette("dark", app_palette)

    assert palette.color(QPalette.ColorRole.Base) == QColor(DARK_SCROLLBACK_BASE)
    assert palette.color(QPalette.ColorRole.Text) == QColor(DARK_SCROLLBACK_TEXT)
    # Distinct from the input-box colors -- output is dimmer than input,
    # matching Potato's own real convention.
    assert palette.color(QPalette.ColorRole.Text) != QColor(DARK_INPUT_TEXT)


def test_light_scrollback_palette_differs_from_dark(qapp):
    dark = scrollback_palette("dark", build_app_palette("dark"))
    light = scrollback_palette("light", build_app_palette("light"))

    assert dark.color(QPalette.ColorRole.Base) != light.color(QPalette.ColorRole.Base)
    assert light.color(QPalette.ColorRole.Base) == QColor(LIGHT_SCROLLBACK_BASE)
    assert light.color(QPalette.ColorRole.Text) == QColor(LIGHT_SCROLLBACK_TEXT)


def test_scrollback_palette_preserves_other_roles_from_base_palette(qapp):
    app_palette = build_app_palette("dark")
    palette = scrollback_palette("dark", app_palette)

    # Only Base/Text are overridden -- everything else (e.g. Highlight
    # for text selection) still comes from the app-wide palette.
    assert palette.color(QPalette.ColorRole.Highlight) == app_palette.color(
        QPalette.ColorRole.Highlight
    )


def test_apply_theme_forces_fusion_style(qapp):
    # Fusion is the one built-in Qt style that reliably honors an
    # explicitly-set QPalette on every widget -- native styles on some
    # real Linux desktops (KDE/qt6ct platform theme integration) can
    # silently override individual widgets' palettes with the system
    # theme instead, which is exactly what a real-desktop test caught.
    apply_theme(qapp, "dark")
    assert qapp.style().objectName().lower() == "fusion"


def test_apply_theme_sets_the_palette_after_the_style_change(qapp):
    # setStyle() resets to the new style's own default palette, so
    # setPalette() must run after it -- otherwise our explicit colors
    # would be immediately overwritten.
    apply_theme(qapp, "dark")
    assert qapp.palette().color(QPalette.ColorRole.Base) == QColor(DARK_INPUT_BASE)


def test_apply_scrollback_theme_sets_the_viewport_palette_too(qapp):
    # The real bug (found via pixel-sampling a real screenshot, not
    # assumed): QTextEdit's visible background is painted by its
    # separate viewport() child widget, which does not reliably pick up
    # a palette set only on the QTextEdit itself.
    text_edit = QTextEdit()
    apply_scrollback_theme(text_edit, "dark")

    assert text_edit.viewport().palette().color(QPalette.ColorRole.Base) == QColor(
        DARK_SCROLLBACK_BASE
    )
    assert text_edit.viewport().autoFillBackground() is True
    assert text_edit.autoFillBackground() is True
