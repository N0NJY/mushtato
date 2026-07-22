"""Headless tests for JSON-file address-book persistence."""

from pathlib import Path

from engine.storage import WorldProfile, load_address_book, save_address_book
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
