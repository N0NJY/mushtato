"""Headless tests for JSON-file settings/hotkey persistence."""

from pathlib import Path

from engine.storage import DEFAULT_HOTKEYS, Settings, load_settings, save_settings


def test_loading_a_missing_file_returns_all_defaults(tmp_path: Path):
    settings = load_settings(tmp_path / "does_not_exist.json")
    assert settings.hotkeys == DEFAULT_HOTKEYS


def test_save_then_load_round_trips(tmp_path: Path):
    path = tmp_path / "settings.json"
    original = Settings(hotkeys={**DEFAULT_HOTKEYS, "spawn_log_window": "Ctrl+Shift+L"})

    save_settings(path, original)
    loaded = load_settings(path)

    assert loaded == original


def test_edit_round_trip_changes_persist(tmp_path: Path):
    path = tmp_path / "settings.json"
    save_settings(path, Settings())

    settings = load_settings(path)
    settings.hotkeys["close_window"] = "Ctrl+Q"
    save_settings(path, settings)

    reloaded = load_settings(path)
    assert reloaded.hotkeys["close_window"] == "Ctrl+Q"


def test_missing_action_in_saved_file_is_filled_in_with_default(tmp_path: Path):
    """Simulates a settings file saved before a new configurable action
    existed -- loading it must not leave the new action unbound.
    """
    path = tmp_path / "settings.json"
    import json

    path.write_text(json.dumps({"hotkeys": {"add_world": "Ctrl+Shift+N"}}), encoding="utf-8")

    settings = load_settings(path)

    assert settings.hotkeys["add_world"] == "Ctrl+Shift+N"
    assert settings.hotkeys["close_window"] == DEFAULT_HOTKEYS["close_window"]


def test_save_is_atomic_no_leftover_tmp_file(tmp_path: Path):
    path = tmp_path / "settings.json"
    save_settings(path, Settings())
    assert path.exists()
    assert not (tmp_path / "settings.json.tmp").exists()
