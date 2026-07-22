"""Headless tests for gui/theme.py's palette construction."""

from gui.theme import (
    DARK_INPUT_BASE,
    DARK_INPUT_TEXT,
    DARK_SCROLLBACK_BASE,
    DARK_SCROLLBACK_TEXT,
    LIGHT_SCROLLBACK_BASE,
    LIGHT_SCROLLBACK_TEXT,
    build_app_palette,
    scrollback_palette,
)
from PySide6.QtGui import QColor, QPalette


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
