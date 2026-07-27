"""Headless tests for gui/version.py -- real bug fixed 2026-07-26:
importlib.metadata.version() only finds a version if the package has
real installed dist-info/egg-info metadata, which is true for a proper
`pip install`, but not for a source run without that step, and not
reliably true for a PyInstaller-frozen build either. Both cases used
to silently show the "dev" placeholder even on a real tagged release.
"""

from importlib.metadata import PackageNotFoundError
from pathlib import Path

import gui.version as version_module
from gui.version import mushtato_version


def test_returns_the_real_installed_package_version_when_available():
    # This project's own dev venv has mushtato installed (pip install
    # -e .), so this exercises the normal, expected path directly.
    assert mushtato_version() != "dev"


def test_falls_back_to_reading_pyproject_toml_when_package_metadata_is_missing(monkeypatch):
    def raise_not_found(name):
        raise PackageNotFoundError(name)

    monkeypatch.setattr(version_module, "_pkg_version", raise_not_found)

    result = mushtato_version()

    assert result != "dev"
    # Matches whatever pyproject.toml's own version field currently is.
    import tomllib

    data = tomllib.loads(
        (Path(version_module.__file__).resolve().parent.parent / "pyproject.toml").read_text(
            encoding="utf-8"
        )
    )
    assert result == data["project"]["version"]


def test_falls_back_to_reading_a_bundled_pyproject_toml_in_a_frozen_build(monkeypatch, tmp_path):
    import shutil
    import sys

    def raise_not_found(name):
        raise PackageNotFoundError(name)

    monkeypatch.setattr(version_module, "_pkg_version", raise_not_found)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    shutil.copy(
        str(Path(version_module.__file__).resolve().parent.parent / "pyproject.toml"),
        str(tmp_path / "pyproject.toml"),
    )

    assert mushtato_version() != "dev"


def test_returns_dev_placeholder_when_neither_source_is_available(monkeypatch, tmp_path):
    def raise_not_found(name):
        raise PackageNotFoundError(name)

    monkeypatch.setattr(version_module, "_pkg_version", raise_not_found)
    monkeypatch.setattr(version_module, "_pyproject_path", lambda: tmp_path / "does_not_exist.toml")

    assert mushtato_version() == "dev"
