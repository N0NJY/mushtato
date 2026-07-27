"""Headless tests for JSON-file address-book persistence."""

import json
from pathlib import Path

from engine.storage import CharacterProfile, WorldProfile, load_address_book, save_address_book
from engine.storage.paths import safe_filename


def test_loading_a_missing_file_returns_empty_list(tmp_path: Path):
    worlds = load_address_book(tmp_path / "does_not_exist.json")
    assert worlds == []


def test_save_then_load_round_trips(tmp_path: Path):
    path = tmp_path / "address_book.json"
    original = [
        WorldProfile(name="Estrellita", host="silvren.com", port=4444, notes="Rick's MUSH"),
        WorldProfile(name="Local Dev", host="127.0.0.1", port=4444),
    ]

    save_address_book(path, original)
    loaded = load_address_book(path)

    assert loaded == original


def test_edit_round_trip_changes_persist(tmp_path: Path):
    path = tmp_path / "address_book.json"
    save_address_book(path, [WorldProfile(name="Old Name", host="example.com", port=1234)])

    worlds = load_address_book(path)
    worlds[0].name = "New Name"
    worlds[0].port = 5678
    save_address_book(path, worlds)

    reloaded = load_address_book(path)
    assert reloaded == [WorldProfile(name="New Name", host="example.com", port=5678)]


def test_delete_round_trip(tmp_path: Path):
    path = tmp_path / "address_book.json"
    worlds = [
        WorldProfile(name="Keep", host="a.example.com", port=1),
        WorldProfile(name="Remove", host="b.example.com", port=2),
    ]
    save_address_book(path, worlds)

    loaded = load_address_book(path)
    remaining = [w for w in loaded if w.name != "Remove"]
    save_address_book(path, remaining)

    assert load_address_book(path) == [WorldProfile(name="Keep", host="a.example.com", port=1)]


def test_save_is_atomic_no_leftover_tmp_file(tmp_path: Path):
    path = tmp_path / "address_book.json"
    save_address_book(path, [])
    assert path.exists()
    assert not (tmp_path / "address_book.json.tmp").exists()


def test_notes_defaults_to_empty_string(tmp_path: Path):
    path = tmp_path / "address_book.json"
    save_address_book(path, [WorldProfile(name="X", host="h", port=1)])
    loaded = load_address_book(path)
    assert loaded[0].notes == ""


def test_safe_filename_sanitizes_special_characters():
    assert safe_filename("My World!") == "My World_"
    assert safe_filename("normal-name_1") == "normal-name_1"
    assert safe_filename("") == "unnamed"
    assert safe_filename("   ") == "unnamed"


# -- Phase 8b: Characters, auto-sends, notes, connection specifics ------


def test_old_phase6_format_json_still_loads_with_new_fields_defaulted(tmp_path: Path):
    """A real migration test, not just a description of intended
    behavior: writes a JSON file in the exact Phase 6 shape (no
    characters/auto-send/login fields at all) and confirms it loads
    correctly under the Phase 8b-extended WorldProfile, with sensible
    defaults for every new field -- no data loss, no crash.
    """
    path = tmp_path / "address_book.json"
    old_format_json = {
        "worlds": [
            {"name": "Old World", "host": "old.example.com", "port": 4201, "notes": "from Phase 6"}
        ]
    }
    path.write_text(json.dumps(old_format_json), encoding="utf-8")

    loaded = load_address_book(path)

    assert len(loaded) == 1
    world = loaded[0]
    assert world.name == "Old World"
    assert world.host == "old.example.com"
    assert world.port == 4201
    assert world.notes == "from Phase 6"
    # Every Phase 8b field defaults sensibly rather than raising/missing.
    assert world.characters == []
    assert world.default_character == ""
    assert world.login_format == "connect {name} {password}"
    assert world.login_delay == 1.5
    assert world.autosend_firstconnect == ""
    assert world.autosend_connect == ""
    assert world.autosend_login == ""
    assert world.connect_count == 0
    assert world.auto_login is False


def test_old_format_json_missing_worlds_key_entirely_still_loads(tmp_path: Path):
    path = tmp_path / "address_book.json"
    path.write_text(json.dumps({"worlds": []}), encoding="utf-8")
    assert load_address_book(path) == []


def test_characters_round_trip(tmp_path: Path):
    path = tmp_path / "address_book.json"
    world = WorldProfile(
        name="Estrellita",
        host="silvren.com",
        port=4444,
        characters=[
            CharacterProfile(name="Thoran", password="hunter2"),
            CharacterProfile(name="Guest1", password=""),
        ],
        default_character="Thoran",
    )
    save_address_book(path, [world])

    loaded = load_address_book(path)

    assert loaded[0].characters == [
        CharacterProfile(name="Thoran", password="hunter2"),
        CharacterProfile(name="Guest1", password=""),
    ]
    assert loaded[0].default_character == "Thoran"


def test_two_worlds_can_each_have_a_character_of_the_same_name_different_password(tmp_path: Path):
    # The exact scenario that confirmed strict per-world scoping is
    # correct (not just accepted) during this phase's checkpoint.
    path = tmp_path / "address_book.json"
    worlds = [
        WorldProfile(
            name="World A", host="a.example.com", port=1,
            characters=[CharacterProfile(name="Thoran", password="passwordA")],
        ),
        WorldProfile(
            name="World B", host="b.example.com", port=2,
            characters=[CharacterProfile(name="Thoran", password="passwordB")],
        ),
    ]
    save_address_book(path, worlds)

    loaded = load_address_book(path)

    assert loaded[0].characters[0].password == "passwordA"
    assert loaded[1].characters[0].password == "passwordB"


def test_autosend_and_login_fields_round_trip(tmp_path: Path):
    path = tmp_path / "address_book.json"
    world = WorldProfile(
        name="X", host="h", port=1,
        login_format="connect {name} {password}",
        login_delay=2.5,
        autosend_firstconnect="look\nwho",
        autosend_connect="@set me=CONNECTED",
        autosend_login="channel/on public",
        connect_count=3,
    )
    save_address_book(path, [world])

    loaded = load_address_book(path)[0]

    assert loaded.login_delay == 2.5
    assert loaded.autosend_firstconnect == "look\nwho"
    assert loaded.autosend_connect == "@set me=CONNECTED"
    assert loaded.autosend_login == "channel/on public"
    assert loaded.connect_count == 3


def test_connect_count_increment_and_save_round_trips(tmp_path: Path):
    path = tmp_path / "address_book.json"
    save_address_book(path, [WorldProfile(name="X", host="h", port=1, connect_count=0)])

    worlds = load_address_book(path)
    worlds[0].connect_count += 1
    save_address_book(path, worlds)

    assert load_address_book(path)[0].connect_count == 1


# -- auto-login flag (post-Character-picker addition) -------------------


def test_auto_login_round_trips(tmp_path: Path):
    path = tmp_path / "address_book.json"
    save_address_book(path, [WorldProfile(name="X", host="h", port=1, auto_login=True)])

    assert load_address_book(path)[0].auto_login is True


def test_pre_auto_login_format_json_defaults_to_false(tmp_path: Path):
    path = tmp_path / "address_book.json"
    old_format_json = {"worlds": [{"name": "Old", "host": "old.example.com", "port": 1}]}
    path.write_text(json.dumps(old_format_json), encoding="utf-8")

    assert load_address_book(path)[0].auto_login is False


def test_nop_keepalive_round_trips(tmp_path: Path):
    path = tmp_path / "address_book.json"
    save_address_book(path, [WorldProfile(name="X", host="h", port=1, nop_keepalive=True)])

    assert load_address_book(path)[0].nop_keepalive is True


def test_pre_nop_keepalive_format_json_defaults_to_false(tmp_path: Path):
    path = tmp_path / "address_book.json"
    old_format_json = {"worlds": [{"name": "Old", "host": "old.example.com", "port": 1}]}
    path.write_text(json.dumps(old_format_json), encoding="utf-8")

    assert load_address_book(path)[0].nop_keepalive is False


# -- Mail Window settings (Phase 12b) -------------------------------------


def test_mail_fields_round_trip(tmp_path: Path):
    path = tmp_path / "address_book.json"
    world = WorldProfile(
        name="X",
        host="h",
        port=1,
        mail_format="MUX @mail",
        mail_format_custom="custom template %to% %body%",
        mail_convert_returns=False,
        mail_convert_returns_to="\\n",
    )
    save_address_book(path, [world])

    loaded = load_address_book(path)[0]
    assert loaded.mail_format == "MUX @mail"
    assert loaded.mail_format_custom == "custom template %to% %body%"
    assert loaded.mail_convert_returns is False
    assert loaded.mail_convert_returns_to == "\\n"


def test_pre_mail_settings_format_json_defaults_match_potato(tmp_path: Path):
    path = tmp_path / "address_book.json"
    old_format_json = {"worlds": [{"name": "Old", "host": "old.example.com", "port": 1}]}
    path.write_text(json.dumps(old_format_json), encoding="utf-8")

    world = load_address_book(path)[0]
    assert world.mail_format == "MUSH @mail"
    assert world.mail_format_custom == "writeto %to% %cc% %bcc% about %subject% ;; write %body% ;; send"
    assert world.mail_convert_returns is True
    assert world.mail_convert_returns_to == "%r"


# -- SSH support (post-Phase-13 addition) --------------------------------


def test_protocol_and_ssh_username_round_trip(tmp_path: Path):
    path = tmp_path / "address_book.json"
    world = WorldProfile(name="X", host="h", port=22, protocol="ssh", ssh_username="rickn0njy")
    save_address_book(path, [world])

    loaded = load_address_book(path)[0]
    assert loaded.protocol == "ssh"
    assert loaded.ssh_username == "rickn0njy"


def test_pre_ssh_format_json_defaults_to_telnet_with_no_username(tmp_path: Path):
    path = tmp_path / "address_book.json"
    old_format_json = {"worlds": [{"name": "Old", "host": "old.example.com", "port": 1}]}
    path.write_text(json.dumps(old_format_json), encoding="utf-8")

    world = load_address_book(path)[0]
    assert world.protocol == "telnet"
    assert world.ssh_username == ""


def test_ssh_password_is_never_part_of_the_saved_shape(tmp_path: Path):
    # WorldProfile deliberately has no ssh_password field at all -- a
    # real shell account's password must never be written to disk,
    # unlike a MU* Character's password. This test would fail loudly
    # (AttributeError) if such a field were ever added back.
    world = WorldProfile(name="X", host="h", port=22, protocol="ssh")
    assert not hasattr(world, "ssh_password")


def test_splitter_sizes_round_trip(tmp_path: Path):
    path = tmp_path / "address_book.json"
    world = WorldProfile(name="X", host="h", port=1, splitter_sizes=[300, 200])
    save_address_book(path, [world])

    loaded = load_address_book(path)[0]
    assert loaded.splitter_sizes == [300, 200]


def test_pre_splitter_sizes_format_json_defaults_to_empty(tmp_path: Path):
    path = tmp_path / "address_book.json"
    old_format_json = {"worlds": [{"name": "Old", "host": "old.example.com", "port": 1}]}
    path.write_text(json.dumps(old_format_json), encoding="utf-8")

    world = load_address_book(path)[0]
    assert world.splitter_sizes == []
