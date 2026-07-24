"""Headless tests for MainWindow as the persistent root shell (Phase
9): closing the host window shuts down every open tab and force-quits
the app, and hotkeys live-reload since there's exactly one owner of
them now.
"""

from pathlib import Path

from PySide6.QtGui import QKeySequence
from PySide6.QtTest import QTest

from engine.storage import load_settings
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


# -- Remembered fonts + splitter size (post-8b addition) -----------------


def test_open_settings_live_reloads_fonts_on_already_open_tabs(qapp, tmp_path: Path, monkeypatch):
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr("gui.windows.main_window.settings_path", lambda: settings_file)

    host = MainWindow(address_book_storage_path=tmp_path / "ab.json")
    tab = host.open_tab("a.example.com", 4000, bridge=FakeBridge())

    class FakeDialog:
        def __init__(self, parent, *, settings):
            self.settings = settings

        def exec(self):
            return 1

        def result_settings(self):
            from engine.storage import Settings

            return Settings(
                hotkeys=self.settings.hotkeys,
                theme=self.settings.theme,
                scrollback_font_family="Courier New",
                scrollback_font_size=14,
                input_font_family="Arial",
                input_font_size=11,
                splitter_sizes=self.settings.splitter_sizes,
            )

    monkeypatch.setattr("gui.windows.main_window.SettingsDialog", FakeDialog)
    host.open_settings()

    assert tab.scrollback.font().family() == "Courier New"
    assert tab.scrollback.font().pointSize() == 14
    assert tab.input_line.font().family() == "Arial"
    assert tab.secondary_input.font().family() == "Arial"
    assert load_settings(settings_file).scrollback_font_family == "Courier New"


def test_open_settings_does_not_resize_already_open_tabs_splitters(qapp, tmp_path: Path, monkeypatch):
    # Splitter size is a per-drag layout tweak, not a Settings-dialog
    # preference -- unlike fonts, it must NOT propagate to tabs that
    # are already open when Settings is saved.
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr("gui.windows.main_window.settings_path", lambda: settings_file)

    host = MainWindow(address_book_storage_path=tmp_path / "ab.json")
    tab = host.open_tab("a.example.com", 4000, bridge=FakeBridge())
    tab.resize(900, 700)
    tab.show()
    from PySide6.QtWidgets import QApplication

    QApplication.processEvents()
    original_sizes = tab.splitter.sizes()

    class FakeDialog:
        def __init__(self, parent, *, settings):
            self.settings = settings

        def exec(self):
            return 1

        def result_settings(self):
            from engine.storage import Settings

            return Settings(
                hotkeys=self.settings.hotkeys,
                theme=self.settings.theme,
                splitter_sizes=[999, 1],
            )

    monkeypatch.setattr("gui.windows.main_window.SettingsDialog", FakeDialog)
    host.open_settings()

    assert tab.splitter.sizes() == original_sizes


def test_record_splitter_sizes_persists_to_disk_after_a_debounce(qapp, tmp_path: Path, monkeypatch):
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr("gui.windows.main_window.settings_path", lambda: settings_file)

    host = MainWindow(address_book_storage_path=tmp_path / "ab.json")

    host.record_splitter_sizes([300, 150])
    assert not settings_file.exists()  # not written immediately -- debounced

    QTest.qWait(600)  # timer interval is 400ms

    assert load_settings(settings_file).splitter_sizes == [300, 150]


def test_rapid_splitter_moves_only_write_once_after_the_debounce_settles(
    qapp, tmp_path: Path, monkeypatch
):
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr("gui.windows.main_window.settings_path", lambda: settings_file)
    host = MainWindow(address_book_storage_path=tmp_path / "ab.json")

    for size in range(10):
        host.record_splitter_sizes([300 + size, 150])

    QTest.qWait(600)

    assert load_settings(settings_file).splitter_sizes == [309, 150]


def test_new_tabs_open_with_the_saved_splitter_sizes(qapp, tmp_path: Path):
    from PySide6.QtWidgets import QApplication

    host = MainWindow(address_book_storage_path=tmp_path / "ab.json", splitter_sizes=[100, 500])
    tab = host.open_tab("a.example.com", 4000, bridge=FakeBridge())
    # tab is a child managed by host.tab_widget's own layout -- give
    # the *host* real geometry (not the tab directly) so that layout
    # actually runs and hands the tab its real size.
    host.resize(900, 700)
    host.show()
    QApplication.processEvents()

    scrollback_size, input_size = tab.splitter.sizes()
    assert input_size > scrollback_size


def test_setting_theme_does_not_clobber_previously_saved_fonts(qapp, tmp_path: Path, monkeypatch):
    # Regression guard: set_theme() used to build a Settings object
    # from only hotkeys+theme, which would silently wipe out any saved
    # font/splitter preferences the next time the theme changed.
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr("gui.windows.main_window.settings_path", lambda: settings_file)
    host = MainWindow(
        address_book_storage_path=tmp_path / "ab.json",
        scrollback_font_family="Courier New",
        scrollback_font_size=14,
    )

    host.set_theme("light")

    assert load_settings(settings_file).scrollback_font_family == "Courier New"
    assert load_settings(settings_file).scrollback_font_size == 14
