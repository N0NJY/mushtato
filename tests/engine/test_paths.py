"""Headless tests for engine/storage/paths.py's directory helpers."""

from engine.storage.paths import drafts_dir, logs_dir, user_data_dir


def test_logs_dir_is_a_subdirectory_of_user_data_dir():
    assert logs_dir() == user_data_dir() / "logs"


def test_drafts_dir_is_a_subdirectory_of_user_data_dir():
    assert drafts_dir() == user_data_dir() / "drafts"
