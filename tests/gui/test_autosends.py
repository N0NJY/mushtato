"""Headless tests for Phase 8b's world-level auto-sends and character
login -- verified against Potato's real dispatch order (potato.tcl's
sendLoginInfoSub): firstconnect (only the world's first-ever connect,
tracked by a persisted counter) -> connect -> character login line ->
login. Uses a real QTimer.singleShot delay (set to 0 in these tests, not
mocked out) plus QTest.qWait to let it actually fire, rather than
calling the internal methods directly and assuming the timer wiring is
correct.
"""

from pathlib import Path

from PySide6.QtTest import QTest

from engine.storage import CharacterProfile, WorldProfile, load_address_book
from gui.windows.main_window import MainWindow
from tests.gui.test_main_window_smoke import FakeBridge


def make_world(**kwargs):
    defaults = dict(name="Test World", host="example.com", port=4201, login_delay=0.0)
    defaults.update(kwargs)
    return WorldProfile(**defaults)


def test_no_world_means_no_autosends(qapp, tmp_path: Path):
    host = MainWindow(address_book_storage_path=tmp_path / "ab.json")
    bridge = FakeBridge()
    host.open_tab("example.com", 4201, bridge=bridge)  # no world= at all
    bridge.connected.emit()
    QTest.qWait(50)
    assert bridge.sent == []


def test_connect_autosend_fires_every_connect(qapp, tmp_path: Path):
    world = make_world(autosend_connect="look\nwho")
    host = MainWindow(address_book_storage_path=tmp_path / "ab.json")
    bridge = FakeBridge()
    host.open_tab("example.com", 4201, bridge=bridge, world=world)

    bridge.connected.emit()
    QTest.qWait(50)

    assert bridge.sent == ["look", "who"]


def test_firstconnect_autosend_only_fires_on_the_very_first_connect(qapp, tmp_path: Path):
    ab_path = tmp_path / "ab.json"
    world = make_world(autosend_firstconnect="welcome script here")
    host = MainWindow(address_book_storage_path=ab_path)
    bridge = FakeBridge()
    host.open_tab("example.com", 4201, bridge=bridge, world=world)

    bridge.connected.emit()
    QTest.qWait(50)
    assert bridge.sent == ["welcome script here"]
    assert world.connect_count == 1

    # A second connect on the SAME world object (e.g. a reconnect)
    # must not fire firstconnect again.
    bridge.sent.clear()
    bridge.connected.emit()
    QTest.qWait(50)
    assert bridge.sent == []
    assert world.connect_count == 2


def test_firstconnect_does_not_fire_again_after_persisted_restart(qapp, tmp_path: Path):
    # The real point of persisting connect_count: even a *fresh*
    # WorldProfile object loaded from disk (simulating a new app
    # session) must not re-fire firstconnect once it's been connected
    # before.
    from engine.storage import save_address_book

    ab_path = tmp_path / "ab.json"
    save_address_book(
        ab_path,
        [make_world(autosend_firstconnect="one time only", connect_count=1)],
    )
    host = MainWindow(address_book_storage_path=ab_path)
    fresh_world = load_address_book(ab_path)[0]
    bridge = FakeBridge()
    host.open_tab("example.com", 4201, bridge=bridge, world=fresh_world)

    bridge.connected.emit()
    QTest.qWait(50)

    assert bridge.sent == []


def test_login_string_sent_for_default_character_with_password_masked_in_scrollback(
    qapp, tmp_path: Path
):
    world = make_world(
        characters=[CharacterProfile(name="Thoran", password="hunter2")],
        default_character="Thoran",
        login_format="connect {name} {password}",
    )
    host = MainWindow(address_book_storage_path=tmp_path / "ab.json")
    bridge = FakeBridge()
    tab = host.open_tab("example.com", 4201, bridge=bridge, world=world)

    bridge.connected.emit()
    QTest.qWait(50)

    assert bridge.sent == ["connect Thoran hunter2"]
    scrollback = tab.scrollback.toPlainText()
    assert "hunter2" not in scrollback
    assert "connect Thoran" in scrollback
    assert "●" * len("hunter2") in scrollback


def test_no_default_character_skips_login_line_but_not_autosends(qapp, tmp_path: Path):
    world = make_world(
        characters=[CharacterProfile(name="Thoran", password="hunter2")],
        default_character="",  # none selected
        autosend_connect="look",
    )
    host = MainWindow(address_book_storage_path=tmp_path / "ab.json")
    bridge = FakeBridge()
    host.open_tab("example.com", 4201, bridge=bridge, world=world)

    bridge.connected.emit()
    QTest.qWait(50)

    assert bridge.sent == ["look"]


def test_explicit_character_overrides_the_world_s_default_without_changing_it(qapp, tmp_path: Path):
    # Post-8b "Log In as" picker: an explicit character passed to
    # open_tab() must win over world.default_character for that one
    # connection, and must never mutate default_character itself.
    thoran = CharacterProfile(name="Thoran", password="hunter2")
    alt = CharacterProfile(name="Alt", password="altpw")
    world = make_world(characters=[thoran, alt], default_character="Thoran")
    host = MainWindow(address_book_storage_path=tmp_path / "ab.json")
    bridge = FakeBridge()
    tab = host.open_tab("example.com", 4201, bridge=bridge, world=world, character=alt)

    bridge.connected.emit()
    QTest.qWait(50)

    assert bridge.sent == ["connect Alt altpw"]
    assert world.default_character == "Thoran"  # unchanged
    assert tab.world.default_character == "Thoran"


def test_full_dispatch_order_matches_potato(qapp, tmp_path: Path):
    world = make_world(
        autosend_firstconnect="firstconnect-line",
        autosend_connect="connect-line",
        autosend_login="login-line",
        characters=[CharacterProfile(name="Thoran", password="pw")],
        default_character="Thoran",
        login_format="connect {name} {password}",
    )
    host = MainWindow(address_book_storage_path=tmp_path / "ab.json")
    bridge = FakeBridge()
    host.open_tab("example.com", 4201, bridge=bridge, world=world)

    bridge.connected.emit()
    QTest.qWait(50)

    assert bridge.sent == [
        "firstconnect-line",
        "connect-line",
        "connect Thoran pw",
        "login-line",
    ]


def test_autosend_lines_bypass_slash_command_processing(qapp, tmp_path: Path):
    # The deliberate deviation from Potato's own send_to (which parses
    # for client commands): an autosend line that looks like a client
    # command must be sent to the server literally, never executed
    # locally -- same principle as the secondary pose/says input box.
    world = make_world(autosend_connect="/quit")
    host = MainWindow(address_book_storage_path=tmp_path / "ab.json")
    bridge = FakeBridge()
    host.open_tab("example.com", 4201, bridge=bridge, world=world)

    bridge.connected.emit()
    QTest.qWait(50)

    assert bridge.sent == ["/quit"]
    assert host.tab_widget.count() == 1  # tab was NOT closed by a local /quit


def test_record_world_connected_persists_across_a_fresh_load(qapp, tmp_path: Path):
    from engine.storage import save_address_book

    ab_path = tmp_path / "ab.json"
    save_address_book(ab_path, [make_world(name="Persisted", connect_count=0)])
    host = MainWindow(address_book_storage_path=ab_path)
    world = load_address_book(ab_path)[0]

    host.record_world_connected(world)

    assert load_address_book(ab_path)[0].connect_count == 1
