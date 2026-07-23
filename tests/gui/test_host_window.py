"""Headless tests for MainWindow as the persistent root shell (Phase
9): closing the host window shuts down every open tab and force-quits
the app, and hotkeys live-reload since there's exactly one owner of
them now.
"""

from pathlib import Path

from PySide6.QtGui import QKeySequence

from gui.windows.main_window import MainWindow
from tests.gui.test_main_window_smoke import FakeBridge


def test_closing_the_host_window_stops_every_tab_s_bridge(qapp, tmp_path: Path):
    host = MainWindow(address_book_storage_path=tmp_path / "ab.json")
    tab_a = host.open_tab("a.example.com", 4000, bridge=FakeBridge())
    tab_b = host.open_tab("b.example.com", 5000, bridge=FakeBridge())
    host.show()

    host.close()

    assert tab_a.bridge.stopped is True
    assert tab_b.bridge.stopped is True


def test_closing_the_host_window_quits_the_application(qapp, tmp_path: Path, monkeypatch):
    host = MainWindow(address_book_storage_path=tmp_path / "ab.json")
    host.show()

    calls = []
    monkeypatch.setattr(qapp, "quit", lambda: calls.append("quit"))

    host.close()

    assert calls == ["quit"]


def test_open_settings_live_reloads_hotkeys(qapp, tmp_path: Path, monkeypatch):
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr("gui.windows.main_window.settings_path", lambda: settings_file)

    host = MainWindow(address_book_storage_path=tmp_path / "ab.json")

    class FakeDialog:
        def __init__(self, parent, *, settings):
            self.settings = settings

        def exec(self):
            return 1

        def result_settings(self):
            from engine.storage import Settings

            return Settings(hotkeys={**self.settings.hotkeys, "close_window": "Ctrl+Shift+W"})

    monkeypatch.setattr("gui.windows.main_window.SettingsDialog", FakeDialog)
    host.open_settings()

    assert host._hotkeys["close_window"] == "Ctrl+Shift+W"
    assert host._hotkey_shortcuts[-1].key() == QKeySequence("Ctrl+Shift+W")
