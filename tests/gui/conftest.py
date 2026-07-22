"""Shared setup for GUI tests: force Qt's offscreen platform so these
run headless (no display needed), matching CLAUDE.md's testing
philosophy that GUI tests shouldn't require a live environment either.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app
