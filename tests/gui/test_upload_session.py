"""Headless tests for UploadSession (Tools > Upload's paced sending
driver) -- built on a real QTimer, but with delay_seconds=0.0 so tests
don't need to actually wait out real wall-clock time; a real
QApplication.processEvents()/QTest.qWait() drains the zero-delay
single-shot timers instead.
"""

from PySide6.QtTest import QTest

from engine.upload_format import UploadOptions
from gui.windows.upload_session import UploadSession


def run_to_completion(session: UploadSession, timeout_ms: int = 2000) -> None:
    finished = []
    session.finished.connect(lambda completed: finished.append(completed))
    session.start()
    elapsed = 0
    while not finished and elapsed < timeout_ms:
        QTest.qWait(10)
        elapsed += 10
    assert finished, "UploadSession never finished"


def test_sends_every_non_blank_line(qapp):
    sent = []
    session = UploadSession(
        "macro.txt", ["one", "", "two"], UploadOptions(), send_line=sent.append
    )
    run_to_completion(session)
    assert sent == ["one", "two"]


def test_finished_signal_reports_true_on_completion(qapp):
    sent = []
    completed = []
    session = UploadSession("f.txt", ["a"], UploadOptions(), send_line=sent.append)
    session.finished.connect(completed.append)
    session.start()
    QTest.qWait(50)
    assert completed == [True]


def test_add_to_history_called_only_when_option_is_set(qapp):
    history = []
    session = UploadSession(
        "f.txt",
        ["a", "b"],
        UploadOptions(add_to_history=True),
        send_line=lambda t: None,
        add_to_history=history.append,
    )
    run_to_completion(session)
    assert history == ["a", "b"]


def test_add_to_history_not_called_when_option_is_off(qapp):
    history = []
    session = UploadSession(
        "f.txt",
        ["a"],
        UploadOptions(add_to_history=False),
        send_line=lambda t: None,
        add_to_history=history.append,
    )
    run_to_completion(session)
    assert history == []


def test_cancel_stops_further_sends_and_reports_false(qapp):
    sent = []
    completed = []
    # A real (small) delay so there's a window to cancel inside, rather
    # than the whole file finishing before cancel() can run.
    session = UploadSession(
        "f.txt", ["a", "b", "c"], UploadOptions(delay_seconds=1.0), send_line=sent.append
    )
    session.finished.connect(completed.append)
    session.start()
    QTest.qWait(50)  # first line has sent; timer is now waiting ~1s for the next
    session.cancel()
    QTest.qWait(50)
    assert sent == ["a"]
    assert completed == [False]


def test_cancel_after_already_finished_is_a_no_op(qapp):
    sent = []
    completed = []
    session = UploadSession("f.txt", ["a"], UploadOptions(), send_line=sent.append)
    session.finished.connect(completed.append)
    run_to_completion(session)
    session.cancel()  # must not emit a second, contradictory "finished(False)"
    assert completed == [True]


def test_show_progress_window_creates_it_lazily_and_reuses_it(qapp):
    session = UploadSession("f.txt", ["a"], UploadOptions(), send_line=lambda t: None)
    window1 = session.show_progress_window()
    window2 = session.show_progress_window()
    assert window1 is window2


def test_progress_window_cancel_button_triggers_session_cancel(qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))

    sent = []
    completed = []
    session = UploadSession(
        "f.txt", ["a", "b", "c"], UploadOptions(delay_seconds=1.0), send_line=sent.append
    )
    session.finished.connect(completed.append)
    session.start()
    QTest.qWait(50)
    window = session.show_progress_window()
    window.cancel_button.click()

    assert completed == [False]
