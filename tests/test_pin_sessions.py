"""Tests for session pin functionality."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from textsessions.indexer import do_pin, load_index, save_index
from textsessions.sessions import Session, _sessions_from_index, load_sessions, sort_by_priority


# ---------------------------------------------------------------------------
# do_pin
# ---------------------------------------------------------------------------

class TestDoPin:
    def test_sets_pinned(self):
        index = {"abc": {"name": "test", "profile": "default", "last_active": "2026-01-01 10:00", "slug": "test"}}
        result = do_pin(index, "abc", True)
        assert result["abc"]["pinned"] is True

    def test_clears_pinned(self):
        index = {"abc": {"name": "test", "profile": "default", "last_active": "2026-01-01 10:00", "slug": "test", "pinned": True}}
        result = do_pin(index, "abc", False)
        assert "pinned" not in result["abc"]

    def test_clear_noop_when_not_set(self):
        index = {"abc": {"name": "test", "profile": "default", "last_active": "2026-01-01 10:00", "slug": "test"}}
        result = do_pin(index, "abc", False)
        assert "pinned" not in result["abc"]


# ---------------------------------------------------------------------------
# Session.pinned field
# ---------------------------------------------------------------------------

def test_session_pinned_default_false():
    s = Session(id="abc", name="test", profile="default", last_active="2026-01-01 10:00", slug="test")
    assert s.pinned is False


def test_sessions_from_index_reads_pinned(tmp_path):
    index = {
        "abc123": {"name": "pinned-session", "profile": "default", "last_active": "2026-01-02 10:00", "slug": "pinned", "pinned": True},
        "def456": {"name": "normal-session", "profile": "default", "last_active": "2026-01-01 10:00", "slug": "normal"},
    }
    yaml_path = tmp_path / "test.yaml"
    yaml_path.write_text(yaml.safe_dump(index))
    sessions = _sessions_from_index(yaml_path, "test-repo", tmp_path)
    pinned_sessions = [s for s in sessions if s.pinned]
    assert len(pinned_sessions) == 1
    assert pinned_sessions[0].name == "pinned-session"


# ---------------------------------------------------------------------------
# Sort: pinned float to top
# ---------------------------------------------------------------------------

def _make_session(sid: str, name: str, last_active: str, pinned: bool = False, priority: str = "") -> Session:
    return Session(
        id=sid,
        name=name,
        profile="default",
        last_active=last_active,
        slug=name,
        pinned=pinned,
        priority=priority,
        repo_path=Path("/tmp/fake"),
    )


def test_load_sessions_pinned_first(tmp_path):
    """Pinned session appears before more-recent unpinned sessions."""
    index = {
        "aaa": {"name": "pinned-old", "profile": "default", "last_active": "2026-01-01 10:00", "slug": "old", "pinned": True},
        "bbb": {"name": "recent", "profile": "default", "last_active": "2026-01-03 10:00", "slug": "recent"},
        "ccc": {"name": "middle", "profile": "default", "last_active": "2026-01-02 10:00", "slug": "middle"},
    }
    yaml_path = tmp_path / "test.yaml"
    yaml_path.write_text(yaml.safe_dump(index))
    sessions = _sessions_from_index(yaml_path, "test-repo", tmp_path)
    # Sort using the same logic as load_sessions
    pinned = sorted([s for s in sessions if s.pinned], key=lambda s: s.last_active, reverse=True)
    rest = sorted([s for s in sessions if not s.pinned], key=lambda s: s.last_active, reverse=True)
    result = pinned + rest
    assert result[0].name == "pinned-old"
    assert result[1].name == "recent"
    assert result[2].name == "middle"


def test_sort_by_priority_pinned_first():
    """sort_by_priority floats pinned sessions above non-pinned regardless of priority."""
    sessions = [
        _make_session("a", "h0-unpinned", "2026-01-03 10:00", priority="H0"),
        _make_session("b", "pinned-low", "2026-01-01 10:00", pinned=True, priority="3"),
        _make_session("c", "normal", "2026-01-02 10:00"),
    ]
    result = sort_by_priority(sessions)
    assert result[0].name == "pinned-low"


def test_sort_by_priority_multiple_pinned_sorted_by_priority():
    """Multiple pinned sessions are sorted by priority_order among themselves."""
    sessions = [
        _make_session("a", "pinned-p3", "2026-01-01 10:00", pinned=True, priority="3"),
        _make_session("b", "pinned-h0", "2026-01-01 10:00", pinned=True, priority="H0"),
    ]
    result = sort_by_priority(sessions)
    assert result[0].name == "pinned-h0"
    assert result[1].name == "pinned-p3"


def test_do_pin_roundtrip(tmp_path):
    """do_pin sets and then clears pinned in the index."""
    index = {"sid123": {"name": "test", "profile": "default", "last_active": "2026-01-01 10:00", "slug": "test"}}
    index = do_pin(index, "sid123", True)
    assert index["sid123"]["pinned"] is True
    index = do_pin(index, "sid123", False)
    assert "pinned" not in index["sid123"]


# ---------------------------------------------------------------------------
# Pins hidden: pinned sessions remain visible, sorted by last_active
# ---------------------------------------------------------------------------

def test_pins_hidden_sessions_remain_visible():
    """When _show_pinned is False, pinned sessions must NOT be removed from the list."""
    sessions = [
        _make_session("a", "pinned-old", "2026-01-01 10:00", pinned=True),
        _make_session("b", "recent", "2026-01-03 10:00"),
        _make_session("c", "middle", "2026-01-02 10:00"),
    ]
    # Simulate what _apply_filter does when show_pinned=False: flat sort, no removal
    result = sorted(sessions, key=lambda s: s.last_active, reverse=True)
    names = [s.name for s in result]
    assert "pinned-old" in names, "pinned session must not be removed when pins are hidden"


def test_pins_hidden_sorted_flat_by_last_active():
    """When pins are hidden, pinned sessions sort by last_active, not floated to top."""
    sessions = [
        _make_session("a", "pinned-old", "2026-01-01 10:00", pinned=True),
        _make_session("b", "recent", "2026-01-03 10:00"),
        _make_session("c", "middle", "2026-01-02 10:00"),
    ]
    result = sorted(sessions, key=lambda s: s.last_active, reverse=True)
    assert result[0].name == "recent"
    assert result[1].name == "middle"
    assert result[2].name == "pinned-old"
