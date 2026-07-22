"""Headless tests for JSON-file script/variable persistence."""

from pathlib import Path

from engine.storage import ScriptRecord, WorldScriptProfile, load_world_scripts, save_world_scripts


def test_loading_a_missing_file_returns_an_empty_profile(tmp_path: Path):
    profile = load_world_scripts(tmp_path / "does_not_exist.json")
    assert profile.scripts == []
    assert profile.variables == {}


def test_save_then_load_round_trips(tmp_path: Path):
    path = tmp_path / "world.json"
    original = WorldScriptProfile(
        scripts=[
            ScriptRecord(name="auto-login", source="send('connect me password')"),
            ScriptRecord(name="local-tool", source="import os", trusted=True, enabled=False),
        ],
        variables={"hp": 100, "name": "Rick"},
    )

    save_world_scripts(path, original)
    loaded = load_world_scripts(path)

    assert loaded.variables == original.variables
    assert [s.name for s in loaded.scripts] == ["auto-login", "local-tool"]
    assert loaded.scripts[1].trusted is True
    assert loaded.scripts[1].enabled is False


def test_save_is_atomic_no_leftover_tmp_file(tmp_path: Path):
    path = tmp_path / "world.json"
    save_world_scripts(path, WorldScriptProfile())
    assert path.exists()
    assert not (tmp_path / "world.json.tmp").exists()


def test_saved_file_is_valid_json_a_human_could_read(tmp_path: Path):
    import json

    path = tmp_path / "world.json"
    save_world_scripts(path, WorldScriptProfile(variables={"x": 1}))
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["variables"] == {"x": 1}
