"""Headless tests for UploadDialog (Tools > Upload / /upload) -- the
options + file-picker dialog modeled on Potato's real
uploadWindowStart/uploadWindowInvoke.
"""

from pathlib import Path

from PySide6.QtWidgets import QMessageBox

from gui.windows.upload_dialog import UploadDialog


def _suppress_critical(monkeypatch) -> None:
    # QMessageBox.critical() is modal and blocks waiting for a real
    # click -- there's no user in this headless test environment to
    # provide one, so it must be stubbed out before triggering a
    # validation-error path, or the test hangs forever.
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: None))


def test_defaults_match_potatos_own(qapp):
    dialog = UploadDialog()
    options = dialog.options()
    assert options.ignore_empty is True
    assert options.mpp_formatted is False
    assert options.add_to_history is False
    assert options.delay_seconds == 0.0
    assert options.prefix == ""


def test_accept_without_a_selected_file_does_not_close_the_dialog(qapp, monkeypatch):
    _suppress_critical(monkeypatch)
    dialog = UploadDialog()
    dialog._on_accept()
    assert dialog.selected_file() == ""


def test_accept_with_a_nonexistent_file_does_not_close_the_dialog(qapp, tmp_path: Path, monkeypatch):
    _suppress_critical(monkeypatch)
    dialog = UploadDialog()
    dialog._selected_file = str(tmp_path / "does_not_exist.txt")
    dialog.file_display.setText(dialog._selected_file)
    dialog._on_accept()
    # result() only reflects Accepted/Rejected after exec(); here we
    # just confirm accept() itself was never reached by checking the
    # dialog is still in its initial (not-yet-a-result) state.
    assert dialog.result() == 0  # QDialog.Rejected is 0, and exec() was never called either


def test_accept_with_a_real_file_succeeds(qapp, tmp_path: Path):
    real_file = tmp_path / "macro.txt"
    real_file.write_text("look\nnorth\n", encoding="utf-8")
    dialog = UploadDialog()
    dialog._selected_file = str(real_file)
    dialog.file_display.setText(str(real_file))
    dialog._on_accept()
    assert dialog.result() == 1  # QDialog.Accepted


def test_selected_directory_falls_back_to_initial_dir_with_no_file(qapp):
    dialog = UploadDialog(initial_dir="/some/starting/dir")
    assert dialog.selected_directory() == "/some/starting/dir"


def test_selected_directory_is_the_chosen_files_parent(qapp, tmp_path: Path):
    real_file = tmp_path / "sub" / "macro.txt"
    real_file.parent.mkdir()
    real_file.write_text("data\n", encoding="utf-8")
    dialog = UploadDialog()
    dialog._selected_file = str(real_file)
    assert dialog.selected_directory() == str(real_file.parent)


def test_options_reflect_the_checked_widgets(qapp):
    dialog = UploadDialog()
    dialog.ignore_empty_checkbox.setChecked(False)
    dialog.mpp_checkbox.setChecked(True)
    dialog.history_checkbox.setChecked(True)
    dialog.delay_spin.setValue(2.5)
    dialog.prefix_edit.setText("say ")

    options = dialog.options()
    assert options.ignore_empty is False
    assert options.mpp_formatted is True
    assert options.add_to_history is True
    assert options.delay_seconds == 2.5
    assert options.prefix == "say "
