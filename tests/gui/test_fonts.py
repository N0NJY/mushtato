"""Headless tests for gui/fonts.py's resolution of the "no override"
sentinels (empty family string / 0 size) that engine/storage/settings.py
stores, since that module can't compute a real font default itself
(no PySide6 import allowed in /engine).
"""

from gui.fonts import default_scrollback_font, resolve_input_font, resolve_scrollback_font


def test_resolve_scrollback_font_with_no_override_matches_the_fixed_width_default(qapp):
    resolved = resolve_scrollback_font("", 0)
    assert resolved.family() == default_scrollback_font().family()


def test_resolve_scrollback_font_with_explicit_family_and_size(qapp):
    resolved = resolve_scrollback_font("Courier New", 14)
    assert resolved.family() == "Courier New"
    assert resolved.pointSize() == 14


def test_resolve_scrollback_font_family_only_leaves_size_untouched(qapp):
    from PySide6.QtGui import QFont

    # size=0 means "no override" -- resolving with just a custom
    # family must not silently force any particular point size.
    resolved = resolve_scrollback_font("Courier New", 0)
    assert resolved.pointSize() == QFont("Courier New").pointSize()


def test_resolve_input_font_with_no_override_uses_default_qfont(qapp):
    from PySide6.QtGui import QFont

    resolved = resolve_input_font("", 0)
    assert resolved.family() == QFont().family()


def test_resolve_input_font_with_explicit_family_and_size(qapp):
    resolved = resolve_input_font("Arial", 16)
    assert resolved.family() == "Arial"
    assert resolved.pointSize() == 16
