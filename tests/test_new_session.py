"""Tests for find_session_created_after."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

from textsessions.indexer import find_session_created_after


PRE_LAUNCH_ID = "aabbccdd1111eeee"
POST_LAUNCH_ID = "ff998877aabb1234"


def _make_index(pre: bool = True, post: bool = True) -> dict:
    index = {}
    if pre:
        index[PRE_LAUNCH_ID] = {
            "name": "old-session",
            "profile": "work",
            "last_active": "2026-04-08 09:00",
            "slug": "old session",
        }
    if post:
        index[POST_LAUNCH_ID] = {
            "name": "new-session",
            "profile": "work",
            "last_active": "2026-04-08 10:05",
            "slug": "new session doing things",
        }
    return index


def test_finds_single_new_session() -> None:
    since = datetime(2026, 4, 8, 10, 0)
    known_ids = {PRE_LAUNCH_ID}
    with patch("textsessions.indexer.load_index", return_value=_make_index()):
        result = find_session_created_after("some-repo", since, known_ids)
    assert result == POST_LAUNCH_ID


def test_returns_none_when_no_new_sessions() -> None:
    since = datetime(2026, 4, 8, 10, 0)
    # Both IDs known before launch
    known_ids = {PRE_LAUNCH_ID, POST_LAUNCH_ID}
    with patch("textsessions.indexer.load_index", return_value=_make_index()):
        result = find_session_created_after("some-repo", since, known_ids)
    assert result is None


def test_returns_none_when_new_session_before_since() -> None:
    # new session's last_active is before since
    since = datetime(2026, 4, 8, 11, 0)
    known_ids = {PRE_LAUNCH_ID}
    with patch("textsessions.indexer.load_index", return_value=_make_index()):
        result = find_session_created_after("some-repo", since, known_ids)
    assert result is None


def test_returns_none_when_multiple_new_sessions() -> None:
    third_id = "1122334455667788"
    index = _make_index()
    index[third_id] = {
        "name": "another-new",
        "profile": "work",
        "last_active": "2026-04-08 10:10",
        "slug": "another new session",
    }
    since = datetime(2026, 4, 8, 10, 0)
    known_ids = {PRE_LAUNCH_ID}
    with patch("textsessions.indexer.load_index", return_value=index):
        result = find_session_created_after("some-repo", since, known_ids)
    assert result is None


def test_new_session_at_exact_since_minute() -> None:
    # last_active == since minute boundary should match (>=)
    since = datetime(2026, 4, 8, 10, 5, 30)  # seconds are stripped
    known_ids = {PRE_LAUNCH_ID}
    with patch("textsessions.indexer.load_index", return_value=_make_index()):
        result = find_session_created_after("some-repo", since, known_ids)
    assert result == POST_LAUNCH_ID
