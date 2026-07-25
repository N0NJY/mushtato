"""Headless tests for SessionTab's Upload wiring (open_upload_dialog,
/upload, and the "only one upload at a time per tab" dispatcher
behavior matching Potato's real uploadWindow).
"""

from pathlib import Path

from PySide6.QtTest import QTest

from gui.windows.session_tab import SessionTab
from tests.gui.test_main_window_smoke import FakeBridge


def make_connected_tab(**kwargs) -> SessionTab:
    bridge = FakeBridge()
    tab = SessionTab("example.com", 4201, bridge=bridge, **kwargs)
    bridge.connected.emit()
    return tab


def test_upload_refuses_when_not_connected(qapp):
    tab = SessionTab("example.com", 4201, bridge=FakeBridge())  # never connected
    tab.open_upload_dialog()
    assert "[Not connected.]" in tab.scrollback.toPlainText()
    assert tab.upload_session is None


def test_cmd_upload_is_registered(qapp, monkeypatch):
    from gui.windows.upload_dialog import UploadDialog

    # /upload reaches open_upload_dialog(), which -- since this tab is
    # connected -- would otherwise construct a real, modal UploadDialog
    # and call exec(), blocking forever with no user to dismiss it in
    # this headless test. Stubbed to immediately "Cancel" so this test
    # can focus on confirming /upload is dispatched as a command at
    # all, not sent to the server as literal text.
    monkeypatch.setattr(UploadDialog, "exec", lambda self: 0)

    tab = make_connected_tab()
    outcome = tab._commands.process("/upload")
    assert outcome.action != "send"  # consumed as a command, not sent to the server


def test_uploading_a_real_file_sends_its_lines(qapp, tmp_path: Path, monkeypatch):
    real_file = tmp_path / "macro.txt"
    real_file.write_text("look\nnorth\n", encoding="utf-8")

    tab = make_connected_tab()

    from gui.windows.upload_dialog import UploadDialog

    def fake_exec(self):
        self._selected_file = str(real_file)
        return 1  # QDialog.Accepted

    monkeypatch.setattr(UploadDialog, "exec", fake_exec)

    tab.open_upload_dialog()
    assert tab.upload_session is not None

    elapsed = 0
    while tab.upload_session is not None and elapsed < 2000:
        QTest.qWait(10)
        elapsed += 10

    assert tab.bridge.sent == ["look", "north"]
    assert "[Upload of \"macro.txt\" complete.]" in tab.scrollback.toPlainText()


def test_reopening_upload_while_in_progress_shows_progress_instead_of_a_new_dialog(
    qapp, tmp_path: Path, monkeypatch
):
    real_file = tmp_path / "big.txt"
    real_file.write_text("one\ntwo\nthree\n", encoding="utf-8")

    tab = make_connected_tab()

    from gui.windows.upload_dialog import UploadDialog
    from engine.upload_format import UploadOptions

    call_count = {"n": 0}

    def fake_exec(self):
        call_count["n"] += 1
        self._selected_file = str(real_file)
        return 1

    monkeypatch.setattr(UploadDialog, "exec", fake_exec)
    # Slow the upload down so it's still running when we reopen it.
    monkeypatch.setattr(UploadDialog, "options", lambda self: UploadOptions(delay_seconds=1.0))

    tab.open_upload_dialog()
    assert call_count["n"] == 1
    session = tab.upload_session
    assert session is not None

    tab.open_upload_dialog()  # should NOT open a second dialog
    assert call_count["n"] == 1
    assert tab.upload_session is session

    session.cancel()


def test_cancelling_an_upload_reports_cancellation(qapp, tmp_path: Path, monkeypatch):
    real_file = tmp_path / "slow.txt"
    real_file.write_text("a\nb\nc\n", encoding="utf-8")

    tab = make_connected_tab()

    from gui.windows.upload_dialog import UploadDialog
    from engine.upload_format import UploadOptions

    monkeypatch.setattr(UploadDialog, "exec", lambda self: (setattr(self, "_selected_file", str(real_file)), 1)[1])
    monkeypatch.setattr(UploadDialog, "options", lambda self: UploadOptions(delay_seconds=1.0))

    tab.open_upload_dialog()
    session = tab.upload_session
    assert session is not None
    QTest.qWait(50)
    session.cancel()

    assert tab.upload_session is None
    assert "[Upload of \"slow.txt\" cancelled.]" in tab.scrollback.toPlainText()


def test_shutdown_cancels_an_in_progress_upload(qapp, tmp_path: Path, monkeypatch):
    real_file = tmp_path / "slow.txt"
    real_file.write_text("a\nb\nc\n", encoding="utf-8")

    tab = make_connected_tab()

    from gui.windows.upload_dialog import UploadDialog
    from engine.upload_format import UploadOptions

    monkeypatch.setattr(UploadDialog, "exec", lambda self: (setattr(self, "_selected_file", str(real_file)), 1)[1])
    monkeypatch.setattr(UploadDialog, "options", lambda self: UploadOptions(delay_seconds=5.0))

    tab.open_upload_dialog()
    assert tab.upload_session is not None

    tab.shutdown()  # must not crash, and must not leave a dangling running timer
    assert tab.upload_session is None
