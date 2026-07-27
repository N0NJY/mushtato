"""Headless tests for gui/asset_paths.py -- resolving gui/assets/
correctly whether running from source or a frozen PyInstaller build.
"""

import sys

from gui.asset_paths import ICON_SIZES, assets_dir, icon_master_path, icon_png_path, splash_path


def test_assets_dir_points_at_the_real_source_tree_dev_mode():
    d = assets_dir()
    assert d.name == "assets"
    assert d.parent.name == "gui"
    assert d.is_dir()


def test_icon_master_path_exists_and_has_real_transparency(qapp):
    # PIL/Pillow isn't a project dependency (checked before, see
    # gui/tray_icon.py's own docstring) -- use Qt's own QImage instead,
    # already a real dependency via PySide6.
    from PySide6.QtGui import QImage

    path = icon_master_path()
    assert path.exists()
    im = QImage(str(path))
    assert im.pixelColor(0, 0).alpha() == 0  # corner is transparent
    assert im.pixelColor(im.width() // 2, im.height() // 2).alpha() == 255  # character isn't


def test_icon_png_path_exists_for_every_standard_size():
    for size in ICON_SIZES:
        path = icon_png_path(size)
        assert path.exists(), f"missing {path}"


def test_splash_path_exists():
    assert splash_path().exists()


def test_assets_dir_uses_meipass_when_frozen(monkeypatch, tmp_path):
    fake_meipass = tmp_path / "frozen_root"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(fake_meipass), raising=False)

    d = assets_dir()

    assert d == fake_meipass / "gui" / "assets"
