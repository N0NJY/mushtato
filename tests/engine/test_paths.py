"""Headless tests for engine/storage/paths.py's directory helpers."""

from engine.storage.paths import logs_dir, user_data_dir


def test_logs_dir_is_a_subdirectory_of_user_data_dir():
    assert logs_dir() == user_data_dir() / "logs"
