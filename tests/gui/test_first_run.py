"""Headless tests for first-run settings detection (Phase 7b)."""

from pathlib import Path

from engine.storage import DEFAULT_THEME, Settings, load_settings, save_settings
from gui.app import ensure_settings, load_app_icon
from gui.asset_paths import ICON_SIZES


class FakeFirstRunDialog:
    """Stands in for SettingsDialog -- records whether it was
    constructed/exec'd, without needing a real modal event loop.
    """

    instances = []

    def __init__(self, *, settings, first_run=False):
        self.settings = settings
        self.first_run = first_run
        self.exec_called = False
        FakeFirstRunDialog.instances.append(self)

    def exec(self):
        self.exec_called = True
        return 1

    def result_settings(self):
        return Settings(theme="light")


def test_first_run_dialog_shown_only_when_no_settings_file_exists(tmp_path: Path):
    FakeFirstRunDialog.instances.clear()
    path = tmp_path / "settings.json"
    assert not path.exists()

    settings = ensure_settings(path, dialog_factory=FakeFirstRunDialog)

    assert len(FakeFirstRunDialog.instances) == 1
    assert FakeFirstRunDialog.instances[0].first_run is True
    assert FakeFirstRunDialog.instances[0].exec_called is True
    assert settings.theme == "light"


def test_first_run_dialog_result_is_saved_to_disk(tmp_path: Path):
    path = tmp_path / "settings.json"

    ensure_settings(path, dialog_factory=FakeFirstRunDialog)

    assert path.exists()
    assert load_settings(path).theme == "light"


def test_no_dialog_shown_when_settings_file_already_exists(tmp_path: Path):
    FakeFirstRunDialog.instances.clear()
    path = tmp_path / "settings.json"
    save_settings(path, Settings(theme="dark"))

    settings = ensure_settings(path, dialog_factory=FakeFirstRunDialog)

    assert FakeFirstRunDialog.instances == []
    assert settings.theme == "dark"


def test_existing_settings_are_returned_unmodified(tmp_path: Path):
    path = tmp_path / "settings.json"
    original = Settings(theme="dark", hotkeys={"add_world": "Ctrl+Shift+N"})
    save_settings(path, original)

    settings = ensure_settings(path, dialog_factory=FakeFirstRunDialog)

    assert settings.hotkeys["add_world"] == "Ctrl+Shift+N"


def test_default_dialog_factory_is_the_real_settings_dialog():
    """Confirms ensure_settings() defaults to the real SettingsDialog
    when no dialog_factory is injected -- the fake above is only for
    tests, not a silent behavior change in production.
    """
    import inspect

    from gui.dialogs.settings_dialog import SettingsDialog

    default = inspect.signature(ensure_settings).parameters["dialog_factory"].default
    assert default is SettingsDialog


def test_load_app_icon_is_not_null_and_has_every_standard_size(qapp):
    icon = load_app_icon()
    assert icon.isNull() is False
    available = {(s.width(), s.height()) for s in icon.availableSizes()}
    for size in ICON_SIZES:
        assert (size, size) in available
