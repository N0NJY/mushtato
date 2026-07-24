"""Headless GUI-level integration tests for Phase 9: engine/scripting
wired into SessionTab for real. Unlike tests/engine/test_line_dispatch.py
(the pure engine-layer trigger/gag/highlight mechanism) and
tests/engine/test_scripting_world.py (ScriptWorld itself), these tests
exercise the actual real widgets -- QTextEdit scrollback content and
character formatting, real FakeBridge simulate_incoming()/
run_in_background() calls, a real QTimer for timer()/autosave -- to
confirm the wiring itself is correct, not just the underlying engine
logic in isolation.

All of these are headless (offscreen Qt, no live server) -- see
test_telnet_bridge_integration.py for the one place this session's
threading claims are verified against a *real* background thread.
"""

from pathlib import Path

from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest

from engine.storage import ScriptRecord, WorldProfile, WorldScriptProfile, save_world_scripts
from gui.windows.main_window import MainWindow
from gui.windows.session_tab import SessionTab
from tests.gui.test_main_window_smoke import FakeBridge


def make_world(**kwargs):
    defaults = dict(name="Test World", host="example.com", port=4201)
    defaults.update(kwargs)
    return WorldProfile(**defaults)


def make_scripted_tab(tmp_path: Path, scripts, *, world=None, bridge=None):
    world = world or make_world()
    store_path = tmp_path / "scripts.json"
    save_world_scripts(store_path, WorldScriptProfile(scripts=scripts))
    tab = SessionTab(
        world.host, world.port, bridge=bridge or FakeBridge(), world=world,
        script_store_path=store_path,
    )
    return tab, store_path


def char_color(text_edit, position):
    cursor = QTextCursor(text_edit.document())
    cursor.setPosition(position)
    cursor.setPosition(position + 1, QTextCursor.MoveMode.KeepAnchor)
    return cursor.charFormat().foreground().color()


# -- The concrete motivating use case: speaker-name highlighting --------


def test_trigger_highlights_speaker_name_in_real_scrollback(qapp, tmp_path: Path):
    source = (
        "def handle(m):\n"
        "    highlight(Style(fg=(255, 0, 0)))\n"
        "on_trigger('^Bob', handle, name='speaker')\n"
    )
    tab, _ = make_scripted_tab(tmp_path, [ScriptRecord(name="speaker", source=source)])

    tab.bridge.simulate_incoming("Bob says hello\r\n")

    text = tab.scrollback.toPlainText()
    assert "Bob says hello" in text
    bob_index = text.index("Bob")
    assert char_color(tab.scrollback, bob_index).getRgb()[:3] == (255, 0, 0)
    other_index = text.index("says")
    assert char_color(tab.scrollback, other_index).getRgb()[:3] != (255, 0, 0)


def test_gag_suppresses_line_in_real_scrollback(qapp, tmp_path: Path):
    source = "on_trigger('spam', lambda m: None, name='spammer', gag=True)\n"
    tab, _ = make_scripted_tab(tmp_path, [ScriptRecord(name="spammer", source=source)])

    tab.bridge.simulate_incoming("this is spam\r\n")
    tab.bridge.simulate_incoming("this is fine\r\n")

    text = tab.scrollback.toPlainText()
    assert "this is spam" not in text
    assert "this is fine" in text


# -- Per-tab independence (checkpoint #2, confirmed at the GUI level) ---


def test_two_tabs_on_the_same_world_have_independent_variables(qapp, tmp_path: Path):
    world = make_world(name="Shared World")
    tab_a, _ = make_scripted_tab(tmp_path, [], world=world)
    tab_b, _ = make_scripted_tab(tmp_path, [], world=world)

    tab_a.script_world.variables["hp"] = 100

    assert "hp" not in tab_b.script_world.variables
    assert tab_a.script_world is not tab_b.script_world
    assert tab_a.script_world.triggers is not tab_b.script_world.triggers


# -- Error/timeout surfacing (Checkpoint 4) ------------------------------


def test_script_load_error_surfaces_and_does_not_crash_construction(qapp, tmp_path: Path):
    bad_source = "def broken(\n"  # invalid syntax
    tab, _ = make_scripted_tab(tmp_path, [ScriptRecord(name="bad", source=bad_source)])

    assert "[Script error loading 'bad'" in tab.scrollback.toPlainText()


def test_trigger_runtime_error_surfaces_to_scrollback(qapp, tmp_path: Path):
    source = "def boom(m):\n    raise ValueError('boom')\non_trigger('fail', boom, name='broken')\n"
    tab, _ = make_scripted_tab(tmp_path, [ScriptRecord(name="s1", source=source)])

    tab.bridge.simulate_incoming("fail\r\n")

    text = tab.scrollback.toPlainText()
    assert "[Script error in trigger 'broken': ValueError: boom]" in text


def test_trigger_auto_disable_surfaces_message_and_signal(qapp, tmp_path: Path):
    source = "def boom(m):\n    raise ValueError('boom')\non_trigger('fail', boom, name='broken')\n"
    tab, _ = make_scripted_tab(tmp_path, [ScriptRecord(name="s1", source=source)])
    disabled_signals = []
    tab.triggerStateChanged.connect(disabled_signals.append)

    for _ in range(5):
        tab.bridge.simulate_incoming("fail\r\n")

    text = tab.scrollback.toPlainText()
    assert "[Trigger 'broken' disabled after 5 consecutive errors - fix and re-save to re-enable]" in text
    assert disabled_signals == ["broken"]
    trigger = tab.script_world.triggers.get("broken")
    assert trigger.enabled is False


def test_matched_alias_intercepts_send(qapp, tmp_path: Path):
    source = "def handle(m):\n    send('go north please')\non_alias('n', handle, name='north-alias')\n"
    tab, _ = make_scripted_tab(tmp_path, [ScriptRecord(name="s1", source=source)])

    tab.input_line.setText("n")
    tab.input_line.returnPressed.emit()

    assert tab.bridge.sent == ["go north please"]


def test_unmatched_alias_falls_back_to_literal_send(qapp, tmp_path: Path):
    source = "def handle(m):\n    send('go north please')\non_alias('n', handle, name='north-alias')\n"
    tab, _ = make_scripted_tab(tmp_path, [ScriptRecord(name="s1", source=source)])

    tab.input_line.setText("look")
    tab.input_line.returnPressed.emit()

    assert tab.bridge.sent == ["look"]


def test_alias_error_surfaces_and_does_not_fall_back_to_literal_send(qapp, tmp_path: Path):
    source = (
        "def boom(m):\n    raise ValueError('alias boom')\n"
        "on_alias('n', boom, name='broken-alias')\n"
    )
    tab, _ = make_scripted_tab(tmp_path, [ScriptRecord(name="s1", source=source)])

    tab.input_line.setText("n")
    tab.input_line.returnPressed.emit()

    assert tab.bridge.sent == []  # never falls back -- see AliasOutcome.error's docstring
    assert "[Script error in alias 'broken-alias': ValueError: alias boom]" in tab.scrollback.toPlainText()


def test_echo_renders_in_real_scrollback(qapp, tmp_path: Path):
    # echo()'s effect crosses a real thread boundary even for an
    # on_connect callback: run_with_timeout() (engine/scripting/
    # sandbox.py) always runs the script body -- any script body,
    # regardless of which "GUI-thread-native" entry point invoked it --
    # on its own internal worker thread while the caller blocks on
    # .join(). _script_echo's signal emission is therefore a genuine
    # cross-thread Qt signal, auto-queued for the GUI thread's event
    # loop rather than delivered inline -- QTest.qWait() lets that
    # queued delivery actually run, same as a real running app's event
    # loop would (just imperceptibly fast there).
    source = "def hello():\n    echo('hello from script')\non_connect(hello)\n"
    tab, _ = make_scripted_tab(tmp_path, [ScriptRecord(name="s1", source=source)])

    tab.bridge.connected.emit()
    QTest.qWait(50)

    assert "hello from script" in tab.scrollback.toPlainText()


def test_timer_fires_and_its_effect_appears(qapp, tmp_path: Path):
    source = "def fire():\n    send('timer fired')\ntimer(0.01, fire)\n"
    tab, _ = make_scripted_tab(tmp_path, [ScriptRecord(name="s1", source=source)])

    QTest.qWait(200)

    assert tab.bridge.sent == ["timer fired"]


def test_on_connect_error_does_not_block_autosends(qapp, tmp_path: Path):
    source = "def boom():\n    raise ValueError('connect boom')\non_connect(boom)\n"
    world = make_world(autosend_connect="look", login_delay=0.0)
    tab, _ = make_scripted_tab(tmp_path, [ScriptRecord(name="s1", source=source)], world=world)

    tab.bridge.connected.emit()
    QTest.qWait(50)

    assert "[Script error in on_connect (boom): ValueError: connect boom]" in tab.scrollback.toPlainText()
    assert tab.bridge.sent == ["look"]  # autosends still ran despite the on_connect failure


# -- Autosave (Checkpoint 1 addendum) ------------------------------------


def test_autosave_only_writes_dirty_tabs(qapp, tmp_path: Path):
    host = MainWindow(
        address_book_storage_path=tmp_path / "ab.json", scripts_dir=tmp_path / "scripts"
    )
    world_a = make_world(name="Dirty World", host="a.example.com", port=1)
    world_b = make_world(name="Clean World", host="b.example.com", port=2)
    tab_a = host.open_tab(world_a.host, world_a.port, bridge=FakeBridge(), world=world_a)
    tab_b = host.open_tab(world_b.host, world_b.port, bridge=FakeBridge(), world=world_b)

    tab_a.script_world._api_set_var("hp", 100)  # the real set_var() API path -- marks dirty
    assert tab_a.script_world.dirty is True
    assert tab_b.script_world.dirty is False

    host._autosave_dirty_scripts()

    assert tab_a.script_world.dirty is False
    assert (tmp_path / "scripts" / "Dirty World.json").exists()
    assert not (tmp_path / "scripts" / "Clean World.json").exists()


def test_save_script_state_on_shutdown_persists_variables(qapp, tmp_path: Path):
    tab, store_path = make_scripted_tab(tmp_path, [])
    tab.script_world._api_set_var("score", 42)

    tab.shutdown()

    from engine.storage import load_world_scripts

    assert load_world_scripts(store_path).variables == {"score": 42}


def test_reload_scripts_resets_a_disabled_trigger(qapp, tmp_path: Path):
    source = "def boom(m):\n    raise ValueError('boom')\non_trigger('fail', boom, name='broken')\n"
    tab, store_path = make_scripted_tab(tmp_path, [ScriptRecord(name="s1", source=source)])
    for _ in range(5):
        tab.bridge.simulate_incoming("fail\r\n")
    assert tab.script_world.triggers.get("broken").enabled is False

    # Simulate re-saving the (unchanged) script via World Properties.
    save_world_scripts(store_path, WorldScriptProfile(scripts=[ScriptRecord(name="s1", source=source)]))
    tab.reload_scripts()

    trigger = tab.script_world.triggers.get("broken")
    assert trigger.enabled is True
    assert trigger.consecutive_failures == 0


# -- Full chain: AddressBookWindow -> MainWindow -> SessionTab ----------
# (the SessionTab-only mechanism is proven above; this confirms the
# real wiring between World Properties and a live, already-open tab,
# using a real MainWindow/AddressBookWindow pair, not FakeHostWindow.)


def test_properties_dialog_shows_disabled_trigger_marker_for_a_live_tab(qapp, tmp_path: Path):
    from PySide6.QtWidgets import QDialog

    from engine.storage import save_address_book
    from gui.dialogs.world_properties_dialog import WorldPropertiesDialog
    from gui.windows.address_book_window import AddressBookWindow

    world = make_world(name="Live World")
    save_address_book(tmp_path / "ab.json", [world])
    source = "def boom(m):\n    raise ValueError('boom')\non_trigger('fail', boom, name='broken')\n"
    save_world_scripts(
        tmp_path / "scripts" / "Live World.json",
        WorldScriptProfile(scripts=[ScriptRecord(name="s1", source=source)]),
    )

    host = MainWindow(
        address_book_storage_path=tmp_path / "ab.json", scripts_dir=tmp_path / "scripts"
    )
    live_tab = host.open_tab(world.host, world.port, bridge=FakeBridge(), world=world)
    for _ in range(5):
        live_tab.bridge.simulate_incoming("fail\r\n")
    assert live_tab.script_world.triggers.get("broken").enabled is False

    address_book = AddressBookWindow(
        host, storage_path=tmp_path / "ab.json", scripts_dir=tmp_path / "scripts"
    )
    address_book.list_widget.setCurrentRow(0)

    seen_markers = {}

    def fake_exec(self):
        seen_markers["tooltip"] = self._scripts_page.list_widget.item(0).toolTip()
        return QDialog.DialogCode.Accepted

    import unittest.mock as mock

    with mock.patch.object(WorldPropertiesDialog, "exec", fake_exec):
        address_book._open_properties()

    assert seen_markers["tooltip"] != ""
    # Re-saving (via _open_properties' own flow, unconditional) must
    # have live-reset the already-open tab's trigger.
    assert live_tab.script_world.triggers.get("broken").enabled is True
    assert live_tab.script_world.triggers.get("broken").consecutive_failures == 0
