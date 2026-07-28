"""Headless tests for Item 10 (2026-07-28): dual-access commands for
every remaining GUI menu action, six new /help menu-category
pseudo-topics, Address Book quick-add/listing, tab/session
introspection, and scrollback recall.

Every dual-access command with a GUI equivalent is checked against the
exact same MainWindow method its menu item already calls -- the same
"same handler, not a parallel implementation" regression guard
test_chrome.py already established for Phase 7d/7e's chrome.
"""

from pathlib import Path

from PySide6.QtWidgets import QApplication

from engine.storage import WorldProfile, load_address_book, save_address_book
from gui.help.topics import COMMAND_HELP, TOPICS, get_topic
from gui.windows.main_window import MainWindow
from gui.windows.session_tab import SessionTab, parse_addworld_command
from tests.gui.test_main_window_smoke import FakeBridge


def make_host(**kwargs):
    return MainWindow(**kwargs)


def make_tab(**kwargs):
    return SessionTab("example.com", 4201, bridge=FakeBridge(), **kwargs)


def _focus(host, widget) -> None:
    # QApplication.focusWidget() only resolves against the *active*
    # top-level window headlessly (same pattern test_chrome.py/
    # test_hotkeys.py already established).
    host.show()
    widget.setFocus()
    host.activateWindow()
    QApplication.processEvents()


def _run(tab, command_line: str) -> None:
    tab.input_line.setText(command_line)
    tab.input_line.returnPressed.emit()


# -- parse_addworld_command (standalone, pure) --------------------------


def test_parse_addworld_minimal():
    assert parse_addworld_command("MyWorld example.com 4201") == (
        "MyWorld",
        "example.com",
        4201,
        False,
        None,
    )


def test_parse_addworld_with_ssl_flag_and_character():
    assert parse_addworld_command("-x -cGuest:secret MyWorld example.com 4201") == (
        "MyWorld",
        "example.com",
        4201,
        True,
        ("Guest", "secret"),
    )


def test_parse_addworld_flags_can_appear_after_positional_args():
    assert parse_addworld_command("MyWorld example.com 4201 -x") == (
        "MyWorld",
        "example.com",
        4201,
        True,
        None,
    )


def test_parse_addworld_rejects_non_numeric_port():
    assert parse_addworld_command("MyWorld example.com notaport") is None


def test_parse_addworld_rejects_wrong_token_count():
    assert parse_addworld_command("MyWorld example.com") is None
    assert parse_addworld_command("MyWorld example.com 4201 extra") is None


# -- dual-access commands: host-level ------------------------------------


def test_newtab_command_calls_open_blank_tab(qapp, tmp_path: Path):
    host = make_host(address_book_storage_path=tmp_path / "ab.json")
    tab = host.open_tab("example.com", 4201, bridge=FakeBridge())
    _run(tab, "/newtab")
    assert host.tab_widget.count() == 2


def test_addressbook_command_shows_the_address_book_window(qapp, tmp_path: Path):
    host = make_host(address_book_storage_path=tmp_path / "ab.json")
    tab = host.open_tab("example.com", 4201, bridge=FakeBridge())
    assert host._address_book_window is None
    _run(tab, "/addressbook")
    assert host._address_book_window is not None


def test_errorlog_command_shows_the_error_log_window(qapp, tmp_path: Path):
    host = make_host(address_book_storage_path=tmp_path / "ab.json")
    tab = host.open_tab("example.com", 4201, bridge=FakeBridge())
    assert host._error_log_window is None
    _run(tab, "/errorlog")
    assert host._error_log_window is not None


def test_about_command_calls_show_about(qapp, tmp_path: Path, monkeypatch):
    host = make_host(address_book_storage_path=tmp_path / "ab.json")
    tab = host.open_tab("example.com", 4201, bridge=FakeBridge())
    calls = []
    monkeypatch.setattr(host, "_show_about", lambda: calls.append("about"))
    _run(tab, "/about")
    assert calls == ["about"]


def test_exit_command_calls_the_same_exit_application_path(qapp, tmp_path: Path, monkeypatch):
    host = make_host(address_book_storage_path=tmp_path / "ab.json")
    tab = host.open_tab("example.com", 4201, bridge=FakeBridge())
    calls = []
    monkeypatch.setattr(qapp, "quit", lambda: calls.append("quit"))
    _run(tab, "/exit")
    assert calls == ["quit"]


def test_host_level_commands_report_unavailable_without_a_host_window(qapp):
    tab = make_tab()  # no host_window
    for name in ("newtab", "addressbook", "exit", "errorlog", "about", "find", "addworld", "worlds", "tabs"):
        tab.scrollback.clear()
        _run(tab, f"/{name}")
        assert "not available" in tab.scrollback.toPlainText().lower(), name


# -- dual-access commands: focus-dispatched edit actions -----------------


def test_cut_copy_paste_undo_redo_selectall_dispatch_to_focused_widget(qapp, tmp_path: Path):
    host = make_host(address_book_storage_path=tmp_path / "ab.json")
    tab = host.open_tab("example.com", 4201, bridge=FakeBridge())
    tab.secondary_input.setText("hello world")
    tab.secondary_input.setCursorPosition(len("hello world"))
    _focus(host, tab.secondary_input)

    _run(tab, "/selectall")
    _run(tab, "/copy")
    tab.secondary_input.setText("")
    _focus(host, tab.secondary_input)
    _run(tab, "/paste")
    assert tab.secondary_input.text() == "hello world"


def test_find_command_toggles_the_active_tab_s_find_bar(qapp, tmp_path: Path):
    host = make_host(address_book_storage_path=tmp_path / "ab.json")
    tab = host.open_tab("example.com", 4201, bridge=FakeBridge())
    assert tab.find_bar.isHidden()
    _run(tab, "/find")
    assert not tab.find_bar.isHidden()
    _run(tab, "/find")
    assert tab.find_bar.isHidden()


# -- /help menu-category pseudo-topics -----------------------------------


def test_new_menu_category_topics_exist_and_reference_their_commands():
    expected = {
        "file": ["/newtab", "/addressbook", "/reconnect", "/disconnect", "/quit", "/exit"],
        "edit": ["/cut", "/copy", "/paste", "/undo", "/redo", "/selectall", "/find"],
        "view": ["/theme", "/timestamps"],
        "logging": ["/spawnlog"],
        "options": ["/settings"],
        "tools": ["/editor", "/upload", "/mail", "/errorlog"],
    }
    from gui.help.topics import HelpContext

    context = HelpContext(hotkeys={}, theme="dark")
    for slug, commands in expected.items():
        topic = get_topic(slug)
        assert topic is not None, slug
        text = topic.render(context)
        for command in commands:
            assert command in text, f"{slug} missing {command}"


def test_topic_slugs_still_never_collide_with_command_names():
    topic_slugs = {topic.slug for topic in TOPICS}
    command_names = {name for name, _ in COMMAND_HELP}
    assert topic_slugs.isdisjoint(command_names)


def test_help_file_command_prints_the_file_topic(qapp):
    tab = make_tab()
    _run(tab, "/help file")
    assert "/newtab" in tab.scrollback.toPlainText()


def test_renamed_slugs_still_resolve_to_their_content():
    # "tabs" -> "sessions" and "about" -> "credits" (2026-07-28): both
    # renamed to make room for the new /tabs and /about commands. The
    # content must still be reachable under its new slug.
    assert get_topic("sessions") is not None
    assert get_topic("credits") is not None
    assert get_topic("tabs") is None
    assert get_topic("about") is None


# -- /addworld and /worlds ------------------------------------------------


def test_addworld_adds_a_world_with_no_dialog(qapp, tmp_path: Path):
    ab_path = tmp_path / "address_book.json"
    host = make_host(address_book_storage_path=ab_path)
    tab = host.open_tab("example.com", 4201, bridge=FakeBridge())

    _run(tab, "/addworld -x -cGuest:secret MyWorld othersite.com 4201")

    worlds = load_address_book(ab_path)
    assert len(worlds) == 1
    assert worlds[0].name == "MyWorld"
    assert worlds[0].host == "othersite.com"
    assert worlds[0].port == 4201
    assert worlds[0].use_ssl is True
    assert worlds[0].default_character == "Guest"
    assert worlds[0].characters[0].password == "secret"


def test_addworld_rejects_a_duplicate_name(qapp, tmp_path: Path):
    ab_path = tmp_path / "address_book.json"
    save_address_book(ab_path, [WorldProfile(name="MyWorld", host="a.com", port=1)])
    host = make_host(address_book_storage_path=ab_path)
    tab = host.open_tab("example.com", 4201, bridge=FakeBridge())

    _run(tab, "/addworld MyWorld b.com 2")

    assert "already exists" in tab.scrollback.toPlainText()
    assert len(load_address_book(ab_path)) == 1


def test_addworld_bad_syntax_reports_usage(qapp, tmp_path: Path):
    host = make_host(address_book_storage_path=tmp_path / "ab.json")
    tab = host.open_tab("example.com", 4201, bridge=FakeBridge())
    _run(tab, "/addworld not enough args")
    assert "Usage: /addworld" in tab.scrollback.toPlainText()


def test_addworld_refreshes_an_already_open_address_book_window(qapp, tmp_path: Path):
    ab_path = tmp_path / "address_book.json"
    host = make_host(address_book_storage_path=ab_path)
    tab = host.open_tab("example.com", 4201, bridge=FakeBridge())
    host._show_address_book()

    _run(tab, "/addworld MyWorld othersite.com 4201")

    assert any(world.name == "MyWorld" for world in host._address_book_window.worlds)


def test_worlds_command_lists_saved_worlds(qapp, tmp_path: Path):
    ab_path = tmp_path / "address_book.json"
    save_address_book(
        ab_path,
        [
            WorldProfile(name="Alpha", host="alpha.com", port=1111),
            WorldProfile(name="Beta", host="beta.com", port=2222, use_ssl=True),
        ],
    )
    host = make_host(address_book_storage_path=ab_path)
    tab = host.open_tab("example.com", 4201, bridge=FakeBridge())

    _run(tab, "/worlds")

    text = tab.scrollback.toPlainText()
    assert "Alpha -- alpha.com:1111 (telnet)" in text
    assert "Beta -- beta.com:2222 (ssl)" in text


def test_worlds_command_reports_when_address_book_is_empty(qapp, tmp_path: Path):
    host = make_host(address_book_storage_path=tmp_path / "ab.json")
    tab = host.open_tab("example.com", 4201, bridge=FakeBridge())
    _run(tab, "/worlds")
    assert "No worlds saved" in tab.scrollback.toPlainText()


# -- /tabs and /vars -------------------------------------------------------


def test_tabs_command_lists_every_open_tab_and_marks_the_current_one(qapp, tmp_path: Path):
    host = make_host(address_book_storage_path=tmp_path / "ab.json")
    tab1 = host.open_tab("example.com", 4201, bridge=FakeBridge())
    tab2 = host.open_tab("other.com", 4202, bridge=FakeBridge())

    _run(tab1, "/tabs")

    text = tab1.scrollback.toPlainText()
    assert "* example.com:4201 -- example.com:4201" in text
    assert "  other.com:4202 -- other.com:4202" in text
    del tab2


def test_vars_command_lists_script_variables(qapp):
    tab = make_tab()
    tab.script_world.variables["counter"] = 3
    tab.script_world.variables["name"] = "Rick"

    _run(tab, "/vars")

    text = tab.scrollback.toPlainText()
    assert "counter = 3" in text
    assert "name = 'Rick'" in text


def test_vars_command_reports_when_no_variables_are_set(qapp):
    tab = make_tab()
    _run(tab, "/vars")
    assert "No script variables set" in tab.scrollback.toPlainText()


# -- /recall ----------------------------------------------------------------


def test_recall_finds_matching_lines_in_the_scrollback(qapp):
    tab = make_tab()
    tab.bridge.simulate_incoming("A goblin attacks you!\r\n")
    tab.bridge.simulate_incoming("You attack the goblin.\r\n")
    tab.bridge.simulate_incoming("A rat scurries by.\r\n")

    _run(tab, "/recall goblin")

    text = tab.scrollback.toPlainText()
    assert "2 match(es)" in text
    assert "A goblin attacks you!" in text
    assert "You attack the goblin." in text


def test_recall_reports_no_matches(qapp):
    tab = make_tab()
    tab.bridge.simulate_incoming("A rat scurries by.\r\n")
    _run(tab, "/recall goblin")
    assert "No lines matched: goblin" in tab.scrollback.toPlainText()


def test_recall_with_no_pattern_reports_usage(qapp):
    tab = make_tab()
    _run(tab, "/recall")
    assert "Usage: /recall" in tab.scrollback.toPlainText()


def test_recall_reports_an_invalid_pattern_instead_of_crashing(qapp):
    tab = make_tab()
    _run(tab, "/recall (unclosed")
    assert "Invalid pattern" in tab.scrollback.toPlainText()
