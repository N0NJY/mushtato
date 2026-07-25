"""Headless tests for the Error Log window (Phase 11) -- displays
engine/errorlog.py's ErrorLog records, with a real Qt signal bridge for
cross-thread-safe live updates (a record can originate from a
background thread via threading.excepthook).
"""

import sys
import threading

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QFileDialog, QMessageBox

from engine.errorlog import ErrorLog
from gui.windows.error_log_window import ErrorLogWindow


def _boom(message="boom"):
    raise RuntimeError(message)


def _log_one(log: ErrorLog, message="boom") -> None:
    try:
        _boom(message)
    except RuntimeError:
        log.log_exception(*sys.exc_info())


def _pump(timeout_seconds=2.0):
    import time

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.01)


def test_window_shows_existing_records_on_construction(qapp, tmp_path):
    log = ErrorLog(log_dir=tmp_path)
    _log_one(log, "already here")

    window = ErrorLogWindow(log)

    assert window.list_widget.count() == 1
    assert "already here" in window.list_widget.item(0).text()


def test_new_error_updates_the_window_live(qapp, tmp_path):
    log = ErrorLog(log_dir=tmp_path)
    window = ErrorLogWindow(log)
    assert window.list_widget.count() == 0

    _log_one(log, "fresh error")

    assert window.list_widget.count() == 1
    assert "fresh error" in window.list_widget.item(0).text()


def test_new_error_from_a_background_thread_reaches_the_window(qapp, tmp_path):
    # The real scenario this signal bridge exists for: threading.
    # excepthook can fire on a thread that isn't the GUI thread.
    log = ErrorLog(log_dir=tmp_path)
    window = ErrorLogWindow(log)

    def emit_from_thread():
        try:
            _boom("from a background thread")
        except RuntimeError:
            log.log_exception(*sys.exc_info())

    thread = threading.Thread(target=emit_from_thread)
    thread.start()
    thread.join()
    _pump()

    assert window.list_widget.count() == 1
    assert "from a background thread" in window.list_widget.item(0).text()


def test_selecting_a_record_shows_its_full_traceback(qapp, tmp_path):
    log = ErrorLog(log_dir=tmp_path)
    _log_one(log, "detail test")
    window = ErrorLogWindow(log)

    window.list_widget.setCurrentRow(0)

    assert "RuntimeError" in window.detail_view.toPlainText()
    assert "detail test" in window.detail_view.toPlainText()


def test_search_filters_the_list(qapp, tmp_path):
    log = ErrorLog(log_dir=tmp_path)
    _log_one(log, "alpha error")
    _log_one(log, "beta error")
    window = ErrorLogWindow(log)
    assert window.list_widget.count() == 2

    window.search_field.setText("alpha")

    assert window.list_widget.count() == 1
    assert "alpha" in window.list_widget.item(0).text()


def test_clear_button_empties_the_list_but_not_the_file(qapp, tmp_path):
    log = ErrorLog(log_dir=tmp_path)
    _log_one(log)
    window = ErrorLogWindow(log)
    assert window.list_widget.count() == 1

    window.clear_errors()

    assert window.list_widget.count() == 0
    assert log.records == []
    files = list(tmp_path.glob("error_*.log"))
    assert len(files) == 1
    assert "boom" in files[0].read_text(encoding="utf-8")


def test_export_writes_currently_listed_records_to_disk(qapp, tmp_path, monkeypatch):
    log = ErrorLog(log_dir=tmp_path)
    _log_one(log, "export me")
    window = ErrorLogWindow(log)

    target = tmp_path / "exported.txt"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), "Text files (*.txt)"))
    )
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))

    window.export_errors()

    content = target.read_text(encoding="utf-8")
    assert "export me" in content
    assert "RuntimeError" in content


def test_export_respects_the_active_search_filter(qapp, tmp_path, monkeypatch):
    log = ErrorLog(log_dir=tmp_path)
    _log_one(log, "keep this one")
    _log_one(log, "filtered out")
    window = ErrorLogWindow(log)
    window.search_field.setText("keep")

    target = tmp_path / "exported.txt"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), "Text files (*.txt)"))
    )
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))

    window.export_errors()

    content = target.read_text(encoding="utf-8")
    assert "keep this one" in content
    assert "filtered out" not in content


def test_export_with_nothing_to_export_does_not_open_a_dialog(qapp, tmp_path, monkeypatch):
    log = ErrorLog(log_dir=tmp_path)
    window = ErrorLogWindow(log)

    called = []
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: called.append(1) or ("", ""))
    )
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))

    window.export_errors()

    assert called == []
