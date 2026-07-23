"""Headless tests for the menu bar / toolbar / status bar chrome on the
host MainWindow (Phase 9: chrome is host-level now, acting on whichever
tab is currently active, rather than per-connection as in Phase 7d).

Every enabled action is expected to call the exact same handler its
typed "/" command, hotkey, or existing button already calls -- these
tests exist to catch a parallel-implementation regression, not just
"the menu exists."
"""

from pathlib import Path

from PySide6.QtWidgets import QMessageBox

from engine.storage import WorldProfile, save_address_book
from gui.version import mushtato_version
from gui.windows.main_window import MainWindow
from tests.gui.test_main_window_smoke import FakeBridge


def make_host(**kwargs):
    return MainWindow(**kwargs)


def test_menu_bar_has_expected_top_level_menus(qapp, tmp_path: Path):
    host = make_host(address_book_storage_path=tmp_path / "ab.json")
    titles = [action.text().replace("&", "") for action in host.menuBar().actions()]
    assert titles == ["File", "Edit", "View", "Logging", "Options", "Tools", "Help"]


def test_address_book_action_is_always_enabled(qapp, tmp_path: Path):
    host = make_host(address_book_storage_path=tmp_path / "ab.json")
    assert host.address_book_action.isEnabled() is True


def test_address_book_action_opens_the_address_book(qapp, tmp_path: Path):
    host = make_host(address_book_storage_path=tmp_path / "ab.json")
    host.address_book_action.trigger()
    assert host._address_book_window is not None
    assert host._address_book_window.isVisible() is True


def test_address_book_action_reuses_the_same_window_on_repeated_clicks(qapp, tmp_path: Path):
    host = make_host(address_book_storage_path=tmp_path / "ab.json")
    host.address_book_action.trigger()
    first = host._address_book_window
    host.address_book_action.trigger()
    assert host._address_book_window is first


def test_settings_action_is_always_enabled(qapp, tmp_path: Path):
    host = make_host(address_book_storage_path=tmp_path / "ab.json")
    assert host.settings_action.isEnabled() is True


def test_settings_action_calls_open_settings(qapp, tmp_path: Path, monkeypatch):
    host = make_host(address_book_storage_path=tmp_path / "ab.json")
    calls = []
    monkeypatch.setattr(host, "open_settings", lambda: calls.append("opened"))
    host.settings_action.trigger()
    assert calls == ["opened"]


def test_chrome_actions_disabled_with_no_tabs_open(qapp, tmp_path: Path):
    host = make_host(address_book_storage_path=tmp_path / "ab.json")
    for action in (
        host.reconnect_action,
        host.disconnect_action,
        host.close_action,
        host.spawn_log_action,
        host.copy_action,
    ):
        assert action.isEnabled() is False


def test_chrome_actions_enabled_once_a_tab_is_open(qapp, tmp_path: Path):
    host = make_host(address_book_storage_path=tmp_path / "ab.json")
    host.open_tab("example.com", 4201, bridge=FakeBridge())
    for action in (
        host.reconnect_action,
        host.disconnect_action,
        host.close_action,
        host.spawn_log_action,
        host.copy_action,
    ):
        assert action.isEnabled() is True


def test_spawnlog_toolbar_action_operates_on_the_active_tab(qapp, tmp_path: Path):
    host = make_host(address_book_storage_path=tmp_path / "ab.json")
    tab = host.open_tab("example.com", 4201, bridge=FakeBridge())
    assert tab.spawn_windows == []
    host.spawn_log_action.trigger()
    assert len(tab.spawn_windows) == 1


def test_close_action_closes_the_active_tab_not_the_window(qapp, tmp_path: Path):
    host = make_host(address_book_storage_path=tmp_path / "ab.json")
    host.open_tab("example.com", 4201, bridge=FakeBridge())
    host.show()
    host.close_action.trigger()
    assert host.tab_widget.count() == 0
    assert host.isVisible() is True


def test_exit_action_closes_the_host_window(qapp, tmp_path: Path):
    host = make_host(address_book_storage_path=tmp_path / "ab.json")
    host.show()
    host.exit_action.trigger()
    assert host.isVisible() is False


def test_disconnect_action_stops_bridge_and_disables_input(qapp, tmp_path: Path):
    host = make_host(address_book_storage_path=tmp_path / "ab.json")
    tab = host.open_tab("example.com", 4201, bridge=FakeBridge())
    host.disconnect_action.trigger()
    assert tab.bridge.stopped is True
    assert tab.input_line.isEnabled() is False


def test_reconnect_action_restarts_the_bridge(qapp, tmp_path: Path):
    host = make_host(address_book_storage_path=tmp_path / "ab.json")
    tab = host.open_tab("example.com", 4201, bridge=FakeBridge())
    host.disconnect_action.trigger()
    host.reconnect_action.trigger()
    assert tab.bridge.started is True
    assert tab.input_line.isEnabled() is True


def test_help_action_opens_the_real_help_window(qapp, tmp_path: Path):
    host = make_host(address_book_storage_path=tmp_path / "ab.json")
    host.help_action.trigger()
    assert host._help_window is not None
    assert host._help_window.isVisible() is True


def test_help_action_works_with_zero_tabs_open(qapp, tmp_path: Path):
    # The Help window is static app documentation, not tied to any one
    # connection -- it must be reachable even before anything is
    # connected, unlike the old Phase 7c placeholder which required an
    # active tab to produce any output at all.
    host = make_host(address_book_storage_path=tmp_path / "ab.json")
    assert host.tab_widget.count() == 0
    host.help_action.trigger()
    assert host._help_window is not None
    assert host._help_window.isVisible() is True


def test_help_action_reuses_the_same_window_on_repeated_clicks(qapp, tmp_path: Path):
    host = make_host(address_book_storage_path=tmp_path / "ab.json")
    host.help_action.trigger()
    first = host._help_window
    host.help_action.trigger()
    assert host._help_window is first


def test_help_window_content_includes_every_topic_and_command(qapp, tmp_path: Path):
    from gui.help.topics import COMMAND_HELP, TOPICS

    host = make_host(address_book_storage_path=tmp_path / "ab.json")
    host.help_action.trigger()
    text = host._help_window.browser.toPlainText()
    for topic in TOPICS:
        assert topic.title in text
    for name, _ in COMMAND_HELP:
        assert f"/{name}" in text


def test_about_action_shows_the_version(qapp, tmp_path: Path, monkeypatch):
    shown = []
    monkeypatch.setattr(
        QMessageBox, "information", staticmethod(lambda parent, title, text: shown.append(text))
    )
    host = make_host(address_book_storage_path=tmp_path / "ab.json")
    host.about_action.trigger()
    assert mushtato_version() in shown[0]


def test_copy_action_copies_the_active_tab_s_selected_scrollback_text(qapp, tmp_path: Path):
    host = make_host(address_book_storage_path=tmp_path / "ab.json")
    tab = host.open_tab("example.com", 4201, bridge=FakeBridge())
    tab.scrollback.selectAll()
    host.copy_action.trigger()
    clipboard_text = qapp.clipboard().text()
    assert "Connecting to example.com:4201" in clipboard_text


def test_placeholder_actions_are_disabled(qapp, tmp_path: Path):
    host = make_host(address_book_storage_path=tmp_path / "ab.json")
    for action in (
        host.find_action,
        host.editor_action,
        host.upload_action,
        host.mail_window_action,
        host.events_action,
    ):
        assert action.isEnabled() is False


def test_theme_menu_reflects_current_theme_and_switching_applies_it(
    qapp, tmp_path: Path, monkeypatch
):
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr("gui.windows.main_window.settings_path", lambda: settings_file)

    host = make_host(theme="dark", address_book_storage_path=tmp_path / "ab.json")
    assert host.dark_theme_action.isChecked() is True
    assert host.light_theme_action.isChecked() is False

    host.light_theme_action.trigger()

    assert host._theme == "light"
    from engine.storage import load_settings

    assert load_settings(settings_file).theme == "light"


def test_switching_theme_re_themes_already_open_tabs(qapp, tmp_path: Path, monkeypatch):
    # Regression guard: previously (Phase 7b) a theme change only ever
    # reached *newly created* windows -- an already-open scrollback
    # kept its construction-time colors. Now that MainWindow has direct
    # access to every open tab, switching theme must restyle them too.
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr("gui.windows.main_window.settings_path", lambda: settings_file)

    from gui.theme import DARK_SCROLLBACK_BASE, LIGHT_SCROLLBACK_BASE
    from PySide6.QtGui import QColor, QPalette

    host = make_host(theme="dark", address_book_storage_path=tmp_path / "ab.json")
    tab = host.open_tab("example.com", 4201, bridge=FakeBridge())
    assert tab.scrollback.palette().color(QPalette.ColorRole.Base) == QColor(DARK_SCROLLBACK_BASE)

    host.light_theme_action.trigger()

    assert tab.scrollback.palette().color(QPalette.ColorRole.Base) == QColor(LIGHT_SCROLLBACK_BASE)


def test_status_bar_shows_no_connection_with_no_tabs(qapp, tmp_path: Path):
    host = make_host(address_book_storage_path=tmp_path / "ab.json")
    assert host.status_name_label.text() == "No connection"


def test_status_bar_shows_host_and_updates_on_connect(qapp, tmp_path: Path):
    host = make_host(address_book_storage_path=tmp_path / "ab.json")
    tab = host.open_tab("example.com", 4201, bridge=FakeBridge())
    assert "example.com:4201" in host.status_addr_label.text()
    assert host.status_state_label.text() == "Connecting"

    tab.bridge.connected.emit()

    assert host.status_state_label.text() == "Connected"


def test_status_bar_shows_disconnected_after_connection_closed(qapp, tmp_path: Path):
    host = make_host(address_book_storage_path=tmp_path / "ab.json")
    tab = host.open_tab("example.com", 4201, bridge=FakeBridge())
    tab.bridge.connected.emit()
    tab.bridge.connectionClosed.emit()
    assert host.status_state_label.text() == "Disconnected"


def test_status_bar_reflects_the_active_tab_when_switching(qapp, tmp_path: Path):
    host = make_host(address_book_storage_path=tmp_path / "ab.json")
    tab_a = host.open_tab("a.example.com", 4000, bridge=FakeBridge())
    host.open_tab("b.example.com", 5000, bridge=FakeBridge())

    host.tab_widget.setCurrentWidget(tab_a)

    assert "a.example.com:4000" in host.status_addr_label.text()


def test_connect_by_name_opens_a_tab_for_a_saved_world(qapp, tmp_path: Path):
    ab_path = tmp_path / "ab.json"
    save_address_book(ab_path, [WorldProfile(name="Estrellita", host="silvren.com", port=4444)])
    host = make_host(address_book_storage_path=ab_path)

    result = host.connect_by_name("Estrellita")

    assert "Connecting" in result
    assert host.tab_widget.count() == 1
    assert host.tab_widget.widget(0).host == "silvren.com"


def test_connect_by_name_with_unknown_world_reports_it(qapp, tmp_path: Path):
    host = make_host(address_book_storage_path=tmp_path / "ab.json")
    result = host.connect_by_name("NoSuchWorld")
    assert "No saved world" in result
    assert host.tab_widget.count() == 0
