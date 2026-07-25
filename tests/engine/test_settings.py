"""Headless tests for JSON-file settings/hotkey persistence."""

from pathlib import Path

from engine.storage import DEFAULT_HOTKEYS, DEFAULT_THEME, Settings, load_settings, save_settings


def test_loading_a_missing_file_returns_all_defaults(tmp_path: Path):
    settings = load_settings(tmp_path / "does_not_exist.json")
    assert settings.hotkeys == DEFAULT_HOTKEYS
    assert settings.theme == DEFAULT_THEME == "dark"


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


def test_theme_round_trips(tmp_path: Path):
    path = tmp_path / "settings.json"
    save_settings(path, Settings(theme="light"))

    reloaded = load_settings(path)

    assert reloaded.theme == "light"


def test_unrecognized_saved_theme_falls_back_to_default(tmp_path: Path):
    """Simulates a hand-edited or future-version settings file with a
    theme value this version doesn't recognize -- must not raise.
    """
    path = tmp_path / "settings.json"
    import json

    path.write_text(json.dumps({"theme": "solarized-nonexistent"}), encoding="utf-8")

    settings = load_settings(path)

    assert settings.theme == DEFAULT_THEME


def test_theme_missing_from_saved_file_defaults(tmp_path: Path):
    """Simulates a settings file saved before theme support existed."""
    path = tmp_path / "settings.json"
    import json

    path.write_text(json.dumps({"hotkeys": DEFAULT_HOTKEYS}), encoding="utf-8")

    settings = load_settings(path)

    assert settings.theme == DEFAULT_THEME


# -- Fonts + splitter size (post-8b addition) ----------------------------


def test_font_and_splitter_fields_default_to_empty_sentinels(tmp_path: Path):
    settings = load_settings(tmp_path / "does_not_exist.json")
    assert settings.scrollback_font_family == ""
    assert settings.scrollback_font_size == 0
    assert settings.input_font_family == ""
    assert settings.input_font_size == 0
    assert settings.splitter_sizes == []


def test_font_and_splitter_fields_round_trip(tmp_path: Path):
    path = tmp_path / "settings.json"
    original = Settings(
        scrollback_font_family="Courier New",
        scrollback_font_size=12,
        input_font_family="Arial",
        input_font_size=11,
        splitter_sizes=[500, 100],
    )

    save_settings(path, original)
    loaded = load_settings(path)

    assert loaded == original


def test_pre_font_settings_format_json_defaults_the_new_fields(tmp_path: Path):
    """Simulates a settings.json saved before font/splitter settings
    existed at all -- must load with sensible defaults, not raise.
    """
    path = tmp_path / "settings.json"
    import json

    path.write_text(json.dumps({"hotkeys": DEFAULT_HOTKEYS, "theme": "dark"}), encoding="utf-8")

    settings = load_settings(path)

    assert settings.scrollback_font_family == ""
    assert settings.scrollback_font_size == 0
    assert settings.input_font_family == ""
    assert settings.input_font_size == 0
    assert settings.splitter_sizes == []


# -- Text Editor settings (Phase 12) --------------------------------------


def test_editor_fields_default_to_sentinels(tmp_path: Path):
    settings = load_settings(tmp_path / "does_not_exist.json")
    assert settings.editor_font_family == ""
    assert settings.editor_font_size == 0
    assert settings.editor_line_numbers is True
    assert settings.editor_word_wrap is True
    assert settings.editor_window_geometry == []
    assert settings.editor_last_dir == ""
    assert settings.upload_last_dir == ""


def test_editor_fields_round_trip(tmp_path: Path):
    path = tmp_path / "settings.json"
    original = Settings(
        editor_font_family="Courier New",
        editor_font_size=14,
        editor_line_numbers=False,
        editor_word_wrap=False,
        editor_window_geometry=[100, 200, 800, 600],
        editor_last_dir="/home/user/drafts",
        upload_last_dir="/home/user/macros",
    )

    save_settings(path, original)
    loaded = load_settings(path)

    assert loaded == original


def test_pre_editor_settings_format_json_defaults_the_new_fields(tmp_path: Path):
    """Simulates a settings.json saved before Phase 12's editor fields
    existed at all -- must load with sensible defaults, not raise.
    """
    path = tmp_path / "settings.json"
    import json

    path.write_text(
        json.dumps(
            {
                "hotkeys": DEFAULT_HOTKEYS,
                "theme": "dark",
                "scrollback_font_family": "",
                "scrollback_font_size": 0,
                "input_font_family": "",
                "input_font_size": 0,
                "splitter_sizes": [],
            }
        ),
        encoding="utf-8",
    )

    settings = load_settings(path)

    assert settings.editor_font_family == ""
    assert settings.editor_font_size == 0
    assert settings.editor_line_numbers is True
    assert settings.editor_word_wrap is True
    assert settings.editor_window_geometry == []
    assert settings.editor_last_dir == ""
    assert settings.upload_last_dir == ""
