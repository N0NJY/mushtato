"""Headless tests for engine/errorlog.py -- the unhandled-exception
crash guard (Phase 11, scoped deliberately narrow per checkpoint: does
NOT mirror errors already shown per-tab, e.g. script/trigger/connection
errors).
"""

import sys
import threading
from pathlib import Path

import pytest

from engine.errorlog import (
    MAX_IN_MEMORY_ERRORS,
    ErrorLog,
    install_excepthook,
    install_thread_excepthook,
)


def _boom():
    raise RuntimeError("boom")


def test_log_exception_adds_a_record(tmp_path: Path):
    log = ErrorLog(log_dir=tmp_path)
    try:
        _boom()
    except RuntimeError:
        log.log_exception(*sys.exc_info())

    assert len(log.records) == 1
    record = log.records[0]
    assert record.level == "CRITICAL"
    assert "boom" in record.message
    assert "RuntimeError" in record.traceback_text


def test_log_exception_writes_to_a_real_day_rotated_file(tmp_path: Path):
    log = ErrorLog(log_dir=tmp_path)
    try:
        _boom()
    except RuntimeError:
        log.log_exception(*sys.exc_info())

    files = list(tmp_path.glob("error_*.log"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert "CRITICAL" in content
    assert "boom" in content


def test_log_file_name_matches_todays_date(tmp_path: Path):
    # No cached/tracked "current day" state at all (a deliberate design
    # change -- see this module's docstring on why the earlier
    # logging.FileHandler-based design was scrapped): every call
    # recomputes the filename fresh from datetime.now(), so day
    # rotation is correct by construction rather than needing tracked
    # state to be invalidated.
    from datetime import datetime

    log = ErrorLog(log_dir=tmp_path)
    try:
        _boom()
    except RuntimeError:
        log.log_exception(*sys.exc_info())

    expected = tmp_path / f"error_{datetime.now():%Y%m%d}.log"
    assert expected.exists()


def test_multiple_exceptions_append_to_the_same_days_file(tmp_path: Path):
    log = ErrorLog(log_dir=tmp_path)
    for _ in range(3):
        try:
            _boom()
        except RuntimeError:
            log.log_exception(*sys.exc_info())

    files = list(tmp_path.glob("error_*.log"))
    assert len(files) == 1
    assert files[0].read_text(encoding="utf-8").count("[CRITICAL]") == 3
    assert len(log.records) == 3


def test_in_memory_records_capped_at_max(tmp_path: Path):
    log = ErrorLog(log_dir=tmp_path)
    for i in range(MAX_IN_MEMORY_ERRORS + 10):
        try:
            raise RuntimeError(f"boom {i}")
        except RuntimeError:
            log.log_exception(*sys.exc_info())

    assert len(log.records) == MAX_IN_MEMORY_ERRORS
    assert "boom 9" not in log.records[0].message  # oldest ones dropped
    assert f"boom {MAX_IN_MEMORY_ERRORS + 9}" in log.records[-1].message


def test_clear_empties_in_memory_but_not_the_file(tmp_path: Path):
    log = ErrorLog(log_dir=tmp_path)
    try:
        _boom()
    except RuntimeError:
        log.log_exception(*sys.exc_info())

    log.clear()

    assert log.records == []
    files = list(tmp_path.glob("error_*.log"))
    assert len(files) == 1
    assert "boom" in files[0].read_text(encoding="utf-8")


def test_listener_fires_on_new_record_and_can_be_removed(tmp_path: Path):
    log = ErrorLog(log_dir=tmp_path)
    seen = []
    listener = seen.append
    log.add_listener(listener)

    try:
        _boom()
    except RuntimeError:
        log.log_exception(*sys.exc_info())
    assert len(seen) == 1

    log.remove_listener(listener)
    try:
        _boom()
    except RuntimeError:
        log.log_exception(*sys.exc_info())
    assert len(seen) == 1  # unchanged -- listener was removed


@pytest.fixture
def restore_sys_excepthook():
    original = sys.excepthook
    yield
    sys.excepthook = original


@pytest.fixture
def restore_threading_excepthook():
    original = threading.excepthook
    yield
    threading.excepthook = original


def test_install_excepthook_logs_and_chains_to_the_previous_hook(
    tmp_path: Path, restore_sys_excepthook
):
    log = ErrorLog(log_dir=tmp_path)
    chained = []
    sys.excepthook = lambda *a: chained.append(a)

    install_excepthook(log)
    try:
        _boom()
    except RuntimeError:
        sys.excepthook(*sys.exc_info())

    assert len(log.records) == 1
    assert len(chained) == 1  # previous hook still ran, not swallowed


def test_install_excepthook_does_not_log_keyboard_interrupt(tmp_path: Path, restore_sys_excepthook):
    log = ErrorLog(log_dir=tmp_path)
    sys.excepthook = lambda *a: None

    install_excepthook(log)
    try:
        raise KeyboardInterrupt()
    except KeyboardInterrupt:
        sys.excepthook(*sys.exc_info())

    assert log.records == []


def test_install_thread_excepthook_logs_a_background_thread_exception(
    tmp_path: Path, restore_threading_excepthook
):
    log = ErrorLog(log_dir=tmp_path)
    install_thread_excepthook(log)

    thread = threading.Thread(target=_boom)
    thread.start()
    thread.join()

    assert len(log.records) == 1
    assert "boom" in log.records[0].message
