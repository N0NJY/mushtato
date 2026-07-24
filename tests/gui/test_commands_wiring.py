"""Headless tests for Phase 7c's built-in command wiring: the primary
input processes "/" commands, the secondary always bypasses them, and
each command calls the exact same handler its GUI equivalent uses.

Phase 7e: commands live on SessionTab; /connect, /settings, and /theme
delegate to the host MainWindow shell that owns the tab.
"""

from pathlib import Path

from engine.storage import WorldProfile, load_settings, save_address_book
from gui.version import mushtato_version
from gui.windows.main_window import MainWindow
from gui.windows.session_tab import SessionTab
from tests.gui.test_main_window_smoke import FakeBridge


def make_tab(**kwargs):
    return SessionTab("example.com", 4201, bridge=FakeBridge(), **kwargs)


def test_plain_text_still_sends_normally(qapp):
    tab = make_tab()
    tab.input_line.setText("look")
    tab.input_line.returnPressed.emit()
    assert tab.bridge.sent == ["look"]


def test_double_slash_escape_sends_literal_slash_text(qapp):
    tab = make_tab()
    tab.input_line.setText("//pose waves")
    tab.input_line.returnPressed.emit()
    assert tab.bridge.sent == ["/pose waves"]


def test_unrecognized_command_shows_error_and_does_not_send(qapp):
    tab = make_tab()
    tab.input_line.setText("/nonsense")
    tab.input_line.returnPressed.emit()
    assert tab.bridge.sent == []
    assert "No such command" in tab.scrollback.toPlainText()


def test_secondary_input_never_processes_commands(qapp):
    """The core dual-input principle: a pose starting with "/" must
    never be reinterpreted as a client command.
    """
    tab = make_tab()
    tab.show()
    tab.secondary_input.setText("/quit")
    tab.secondary_input.returnPressed.emit()

    assert tab.bridge.sent == ["/quit"]  # sent to the MUD literally, not executed


def test_quit_command_calls_the_same_close_method_as_the_hotkey(qapp, tmp_path: Path):
    host = MainWindow(address_book_storage_path=tmp_path / "ab.json")
    tab = host.open_tab("example.com", 4201, bridge=FakeBridge())
    tab.input_line.setText("/quit")
    tab.input_line.returnPressed.emit()
    assert host.tab_widget.count() == 0


def test_spawnlog_command_calls_the_same_method_as_the_button(qapp):
    tab = make_tab()
    assert tab.spawn_windows == []
    tab.input_line.setText("/spawnlog")
    tab.input_line.returnPressed.emit()
    assert len(tab.spawn_windows) == 1


def test_version_command_matches_the_about_dialog_s_string(qapp):
    tab = make_tab()
    tab.input_line.setText("/version")
    tab.input_line.returnPressed.emit()
    assert mushtato_version() in tab.scrollback.toPlainText()


def test_help_lists_all_registered_built_in_commands(qapp):
    tab = make_tab()
    tab.input_line.setText("/help")
    tab.input_line.returnPressed.emit()
    text = tab.scrollback.toPlainText()
    for name in ("/quit", "/spawnlog", "/connect", "/settings", "/version", "/theme"):
        assert name in text


def test_bare_help_opens_the_help_window(qapp, tmp_path: Path):
    host = MainWindow(address_book_storage_path=tmp_path / "ab.json")
    tab = host.open_tab("example.com", 4201, bridge=FakeBridge())
    tab.input_line.setText("/help")
    tab.input_line.returnPressed.emit()
    assert host._help_window is not None
    assert host._help_window.isVisible() is True


def test_help_topics_lists_topic_slugs_without_opening_the_window(qapp, tmp_path: Path):
    from gui.help.topics import TOPICS

    host = MainWindow(address_book_storage_path=tmp_path / "ab.json")
    tab = host.open_tab("example.com", 4201, bridge=FakeBridge())
    tab.input_line.setText("/help topics")
    tab.input_line.returnPressed.emit()
    text = tab.scrollback.toPlainText()
    for topic in TOPICS:
        assert topic.slug in text
    assert host._help_window is None  # /help topics doesn't open the window


def test_help_topic_prints_that_topic_s_content_to_the_scrollback(qapp):
    tab = make_tab()
    tab.input_line.setText("/help hotkeys")
    tab.input_line.returnPressed.emit()
    text = tab.scrollback.toPlainText()
    assert "Hotkeys" in text
    assert "Spawn Log Window" in text  # a real current hotkey label
    # Markdown syntax should be stripped for scrollback display.
    assert "**" not in text.split("Connecting to")[-1]


def test_help_command_name_still_shows_its_one_liner(qapp):
    tab = make_tab()
    tab.input_line.setText("/help theme")
    tab.input_line.returnPressed.emit()
    assert "Switch theme: /theme [dark|light]" in tab.scrollback.toPlainText()


def test_help_unknown_name_reports_neither_topic_nor_command(qapp):
    tab = make_tab()
    tab.input_line.setText("/help bogus")
    tab.input_line.returnPressed.emit()
    assert "No such help topic or command: bogus" in tab.scrollback.toPlainText()


def test_topic_slugs_never_collide_with_command_names(qapp):
    from gui.help.topics import COMMAND_HELP, TOPICS

    topic_slugs = {topic.slug for topic in TOPICS}
    command_names = {name for name, _ in COMMAND_HELP}
    assert topic_slugs.isdisjoint(command_names)


def test_connect_and_settings_report_unavailable_without_a_host_window(qapp):
    tab = make_tab()  # no host_window -> standalone test scenario

    tab.input_line.setText("/connect somewhere")
    tab.input_line.returnPressed.emit()
    assert "not available" in tab.scrollback.toPlainText().lower()

    tab.input_line.setText("/settings")
    tab.input_line.returnPressed.emit()
    assert tab.scrollback.toPlainText().lower().count("not available") == 2


def test_connect_command_calls_the_same_open_tab_as_the_address_book(qapp, tmp_path: Path):
    ab_path = tmp_path / "address_book.json"
    save_address_book(ab_path, [WorldProfile(name="Estrellita", host="silvren.com", port=4444)])
    host = MainWindow(address_book_storage_path=ab_path, scripts_dir=tmp_path / "scripts")
    tab = host.open_tab("example.com", 4201, bridge=FakeBridge())

    tab.input_line.setText("/connect Estrellita")
    tab.input_line.returnPressed.emit()

    assert host.tab_widget.count() == 2
    new_tab = host.tab_widget.widget(1)
    assert new_tab.host == "silvren.com"


def test_connect_command_with_unknown_world_name_reports_it(qapp, tmp_path: Path):
    ab_path = tmp_path / "address_book.json"
    save_address_book(ab_path, [WorldProfile(name="Estrellita", host="silvren.com", port=4444)])
    host = MainWindow(address_book_storage_path=ab_path, scripts_dir=tmp_path / "scripts")
    tab = host.open_tab("example.com", 4201, bridge=FakeBridge())

    tab.input_line.setText("/connect NoSuchWorld")
    tab.input_line.returnPressed.emit()

    assert host.tab_widget.count() == 1
    assert "No saved world" in tab.scrollback.toPlainText()


def test_settings_command_opens_the_same_dialog_path(qapp, tmp_path: Path, monkeypatch):
    host = MainWindow(address_book_storage_path=tmp_path / "ab.json")
    tab = host.open_tab("example.com", 4201, bridge=FakeBridge())

    calls = []
    monkeypatch.setattr(host, "open_settings", lambda: calls.append("opened"))

    tab.input_line.setText("/settings")
    tab.input_line.returnPressed.emit()

    assert calls == ["opened"]


def test_theme_command_persists_and_applies_the_new_theme(qapp, tmp_path: Path, monkeypatch):
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr("gui.windows.main_window.settings_path", lambda: settings_file)

    host = MainWindow(address_book_storage_path=tmp_path / "ab.json", theme="dark")
    tab = host.open_tab("example.com", 4201, bridge=FakeBridge())
    tab.input_line.setText("/theme light")
    tab.input_line.returnPressed.emit()

    assert load_settings(settings_file).theme == "light"
    assert "light" in tab.scrollback.toPlainText()


def test_theme_command_rejects_an_invalid_value(qapp):
    tab = make_tab()
    tab.input_line.setText("/theme neon")
    tab.input_line.returnPressed.emit()
    assert "Usage" in tab.scrollback.toPlainText()


def test_disconnect_command_stops_the_bridge(qapp):
    tab = make_tab()
    tab.input_line.setText("/disconnect")
    tab.input_line.returnPressed.emit()
    assert tab.bridge.stopped is True
    assert tab.input_line.isEnabled() is False


def test_reconnect_command_restarts_the_bridge(qapp):
    tab = make_tab()
    tab.input_line.setText("/disconnect")
    tab.input_line.returnPressed.emit()
    tab.input_line.setEnabled(True)  # re-enable manually since it's disabled after disconnect
    tab.input_line.setText("/reconnect")
    tab.input_line.returnPressed.emit()
    assert tab.bridge.started is True
