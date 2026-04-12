"""Unit tests for textsessions.indexer."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from textsessions.indexer import (
    build_index,
    delete_session,
    do_priority,
    do_rename,
    do_tag,
    do_tags,
    do_untag,
    load_index,
    make_completion_name,
    make_slug,
    resolve_session_id,
    save_index,
    scan_sessions,
    write_legacy_tsv,
)


# ---------------------------------------------------------------------------
# make_slug
# ---------------------------------------------------------------------------

class TestMakeSlug:
    def test_strips_leading_filler(self):
        assert make_slug("Can you help me with X") == "help me with X"

    def test_truncates_at_word_boundary(self):
        result = make_slug("a " * 30, max_len=10)
        assert len(result) <= 13  # "a a a a a..."
        assert result.endswith("...")

    def test_strips_html(self):
        assert "<b>" not in make_slug("<b>bold text</b>")

    def test_collapses_whitespace(self):
        assert "  " not in make_slug("foo   bar\n  baz")

    def test_short_string_unchanged(self):
        assert make_slug("hello") == "hello"

    def test_strips_hey_hi(self):
        assert not make_slug("hey can you do X").startswith("hey")


# ---------------------------------------------------------------------------
# make_completion_name
# ---------------------------------------------------------------------------

class TestMakeCompletionName:
    def test_lowercase_hyphenated(self):
        assert make_completion_name("Hello World") == "hello-world"

    def test_strips_special_chars(self):
        assert make_completion_name("foo! bar? baz.") == "foo-bar-baz"

    def test_no_leading_trailing_hyphens(self):
        name = make_completion_name("  -- foo --  ")
        assert not name.startswith("-")
        assert not name.endswith("-")

    def test_max_length(self):
        assert len(make_completion_name("x " * 40)) <= 60


# ---------------------------------------------------------------------------
# scan_sessions
# ---------------------------------------------------------------------------

@pytest.fixture
def jsonl_dir(tmp_path):
    """Creates a fake sessions directory with one .jsonl file."""
    claude_dir = tmp_path / ".claude"
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()

    sid = "a" * 32
    lines = [
        json.dumps({"type": "user", "timestamp": "2026-01-01T10:00:00Z",
                    "message": {"content": "Hello, help me refactor this module"}}),
        json.dumps({"type": "assistant", "timestamp": "2026-01-01T10:00:05Z",
                    "message": {"content": "Sure!"}}),
        json.dumps({"type": "user", "timestamp": "2026-01-01T10:01:00Z",
                    "message": {"content": "Also add tests"}}),
    ]
    (sessions_dir / f"{sid}.jsonl").write_text("\n".join(lines))
    return claude_dir, sessions_dir, sid


def test_scan_sessions_basic(jsonl_dir):
    claude_dir, sessions_dir, sid = jsonl_dir
    pairs = [f"{claude_dir}::{sessions_dir}"]
    results = scan_sessions(pairs)
    assert len(results) == 1
    assert results[0]["id"] == sid
    assert "refactor" in results[0]["combined"].lower()


def test_scan_sessions_custom_title(jsonl_dir):
    claude_dir, sessions_dir, sid = jsonl_dir
    # Prepend a custom-title entry
    path = sessions_dir / f"{sid}.jsonl"
    existing = path.read_text()
    path.write_text(
        json.dumps({"type": "custom-title", "customTitle": "My Refactor Session", "timestamp": "2026-01-01T09:59:00Z"})
        + "\n" + existing
    )
    results = scan_sessions([f"{claude_dir}::{sessions_dir}"])
    assert results[0]["custom_title"] == "My Refactor Session"


def test_scan_sessions_skips_empty(tmp_path):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    (sessions_dir / "empty.jsonl").write_text("")
    results = scan_sessions([f"{tmp_path / '.claude'}::{sessions_dir}"])
    assert results == []


def test_scan_sessions_skips_slash_messages(tmp_path):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    lines = [
        json.dumps({"type": "user", "timestamp": "2026-01-01T10:00:00Z",
                    "message": {"content": "/compact"}}),
    ]
    (sessions_dir / ("x" * 32 + ".jsonl")).write_text("\n".join(lines))
    results = scan_sessions([f"{tmp_path / '.claude'}::{sessions_dir}"])
    assert results == []


# ---------------------------------------------------------------------------
# build_index
# ---------------------------------------------------------------------------

def test_build_index_creates_entries(jsonl_dir, tmp_path):
    claude_dir, sessions_dir, sid = jsonl_dir
    state_dir = tmp_path / "state"
    pairs = [f"{claude_dir}::{sessions_dir}"]
    with patch("textsessions.indexer.STATE_DIR", state_dir), \
         patch("textsessions.indexer.LEGACY_INDEX_DIR", tmp_path / "legacy"):
        index = build_index("test-repo", pairs)
    assert sid in index
    assert "name" in index[sid]
    assert "slug" in index[sid]


def test_build_index_preserves_tags(jsonl_dir, tmp_path):
    claude_dir, sessions_dir, sid = jsonl_dir
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    # Pre-seed index with tags on the session
    existing = {sid: {"name": "old", "profile": "default", "last_active": "2026-01-01 10:00", "slug": "old", "tags": ["important"]}}
    (state_dir / "test-repo.yaml").write_text(yaml.safe_dump(existing))
    pairs = [f"{claude_dir}::{sessions_dir}"]
    with patch("textsessions.indexer.STATE_DIR", state_dir), \
         patch("textsessions.indexer.LEGACY_INDEX_DIR", tmp_path / "legacy"):
        index = build_index("test-repo", pairs)
    assert "important" in index[sid].get("tags", [])


def test_build_index_preserves_priority(jsonl_dir, tmp_path):
    claude_dir, sessions_dir, sid = jsonl_dir
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    existing = {sid: {"name": "old", "profile": "default", "last_active": "2026-01-01 10:00", "slug": "old", "priority": "H0"}}
    (state_dir / "test-repo.yaml").write_text(yaml.safe_dump(existing))
    pairs = [f"{claude_dir}::{sessions_dir}"]
    with patch("textsessions.indexer.STATE_DIR", state_dir), \
         patch("textsessions.indexer.LEGACY_INDEX_DIR", tmp_path / "legacy"):
        index = build_index("test-repo", pairs)
    assert index[sid].get("priority") == "H0"


def test_build_index_preserves_all_user_fields(jsonl_dir, tmp_path):
    """All user-set fields survive a second build_index call."""
    claude_dir, sessions_dir, sid = jsonl_dir
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    pairs = [f"{claude_dir}::{sessions_dir}"]
    # First build: no prior state
    with patch("textsessions.indexer.STATE_DIR", state_dir), \
         patch("textsessions.indexer.LEGACY_INDEX_DIR", tmp_path / "legacy"):
        index = build_index("test-repo", pairs)

    # Simulate user mutating several fields
    index[sid]["priority"] = "1"
    index[sid]["tags"] = ["keep-me"]
    index[sid]["pinned"] = True
    index[sid]["archived"] = True
    index[sid]["name"] = "my-custom-name"
    (state_dir / "test-repo.yaml").write_text(yaml.safe_dump(index))

    # Second build: fields must survive
    with patch("textsessions.indexer.STATE_DIR", state_dir), \
         patch("textsessions.indexer.LEGACY_INDEX_DIR", tmp_path / "legacy"):
        index2 = build_index("test-repo", pairs)

    assert index2[sid].get("priority") == "1"
    assert "keep-me" in index2[sid].get("tags", [])
    assert index2[sid].get("pinned") is True
    assert index2[sid].get("archived") is True
    assert index2[sid].get("name") == "my-custom-name"


def test_build_index_auto_renames_hex_sessions(tmp_path):
    """build_index upgrades hex-stub names when custom-title exists in .jsonl."""
    claude_dir = tmp_path / ".claude"
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    sid = "ab12cd" + "0" * 26  # 32-char hex ID → name will be "ab12c" (first 5)
    lines = [
        json.dumps({"type": "user", "timestamp": "2026-01-01T10:00:00Z",
                    "message": {"content": "Help me with auth"}}),
        json.dumps({"type": "custom-title", "timestamp": "2026-01-01T10:01:00Z",
                    "customTitle": "Auth refactor for login flow"}),
    ]
    (sessions_dir / f"{sid}.jsonl").write_text("\n".join(lines))
    state_dir = tmp_path / "state"
    pairs = [f"{claude_dir}::{sessions_dir}"]
    with patch("textsessions.indexer.STATE_DIR", state_dir), \
         patch("textsessions.indexer.LEGACY_INDEX_DIR", tmp_path / "legacy"):
        index = build_index("test-repo", pairs)
    # Name should be derived from custom title, not the hex stub
    assert index[sid]["name"] != sid[:5]
    assert "auth" in index[sid]["name"].lower()


def test_build_index_keeps_user_name_over_auto_rename(tmp_path):
    """If user explicitly renamed a session, auto-rename does not overwrite."""
    claude_dir = tmp_path / ".claude"
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    sid = "ab12cd" + "0" * 26
    lines = [
        json.dumps({"type": "user", "timestamp": "2026-01-01T10:00:00Z",
                    "message": {"content": "Help me with auth"}}),
        json.dumps({"type": "custom-title", "timestamp": "2026-01-01T10:01:00Z",
                    "customTitle": "Auth refactor for login flow"}),
    ]
    (sessions_dir / f"{sid}.jsonl").write_text("\n".join(lines))
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    # Pre-seed with a non-hex user-set name
    existing = {sid: {"name": "my-auth-work", "profile": "default", "last_active": "2026-01-01 10:00", "slug": "old"}}
    (state_dir / "test-repo.yaml").write_text(yaml.safe_dump(existing))
    pairs = [f"{claude_dir}::{sessions_dir}"]
    with patch("textsessions.indexer.STATE_DIR", state_dir), \
         patch("textsessions.indexer.LEGACY_INDEX_DIR", tmp_path / "legacy"):
        index = build_index("test-repo", pairs)
    # User-set name preserved (not hex, so auto-rename doesn't trigger)
    assert index[sid]["name"] == "my-auth-work"


# ---------------------------------------------------------------------------
# load_index / save_index
# ---------------------------------------------------------------------------

def test_load_index_missing_returns_empty(tmp_path):
    with patch("textsessions.indexer.STATE_DIR", tmp_path):
        result = load_index("nonexistent")
    assert result == {}


def test_save_and_load_roundtrip(tmp_path):
    index = {"abc123": {"name": "test", "profile": "default", "last_active": "2026-01-01 10:00", "slug": "test slug"}}
    with patch("textsessions.indexer.STATE_DIR", tmp_path):
        save_index("my-repo", index)
        loaded = load_index("my-repo")
    assert loaded == index


# ---------------------------------------------------------------------------
# Mutation functions
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_index():
    return {
        "aaa": {"name": "aaaaa", "profile": "default", "last_active": "2026-01-01 10:00", "slug": "hello world"},
        "bbb": {"name": "bbbbb", "profile": "work", "last_active": "2026-01-02 10:00", "slug": "fix the bug"},
    }


class TestDoTag:
    def test_adds_tag(self, sample_index):
        idx = do_tag(sample_index, "aaa", "daily")
        assert "daily" in idx["aaa"]["tags"]

    def test_adds_multiple_tags(self, sample_index):
        idx = do_tag(sample_index, "aaa", "daily,recurrent")
        assert "daily" in idx["aaa"]["tags"]
        assert "recurrent" in idx["aaa"]["tags"]

    def test_deduplicates(self, sample_index):
        sample_index["aaa"]["tags"] = ["daily"]
        idx = do_tag(sample_index, "aaa", "daily,new")
        assert idx["aaa"]["tags"].count("daily") == 1
        assert "new" in idx["aaa"]["tags"]


class TestDoUntag:
    def test_removes_tag(self, sample_index):
        sample_index["aaa"]["tags"] = ["daily", "old"]
        idx = do_untag(sample_index, "aaa", "old")
        assert "old" not in idx["aaa"]["tags"]
        assert "daily" in idx["aaa"]["tags"]

    def test_removes_tags_key_when_empty(self, sample_index):
        sample_index["aaa"]["tags"] = ["only"]
        idx = do_untag(sample_index, "aaa", "only")
        assert "tags" not in idx["aaa"]


class TestDoPriority:
    def test_sets_priority(self, sample_index):
        idx = do_priority(sample_index, "aaa", "H0")
        assert idx["aaa"]["priority"] == "H0"

    def test_clears_priority(self, sample_index):
        sample_index["aaa"]["priority"] = "1"
        idx = do_priority(sample_index, "aaa", "clear")
        assert "priority" not in idx["aaa"]

    def test_invalid_priority_raises(self, sample_index):
        with pytest.raises(ValueError):
            do_priority(sample_index, "aaa", "X9")


class TestDoRename:
    def test_updates_slug(self, sample_index):
        idx = do_rename(sample_index, "aaa", "New Title For This Session")
        assert "New Title" in idx["aaa"]["slug"] or "new-title" in idx["aaa"]["name"]

    def test_updates_name(self, sample_index):
        idx = do_rename(sample_index, "aaa", "My Renamed Session")
        assert idx["aaa"]["name"] == "my-renamed-session"


class TestDoTags:
    def test_counts_tags(self, sample_index):
        sample_index["aaa"]["tags"] = ["daily", "work"]
        sample_index["bbb"]["tags"] = ["daily"]
        counts = do_tags(sample_index)
        assert counts["daily"] == 2
        assert counts["work"] == 1

    def test_empty_index(self):
        assert do_tags({}) == {}


class TestDeleteSession:
    def test_removes_session(self, sample_index):
        idx = delete_session(sample_index, "aaa")
        assert "aaa" not in idx

    def test_missing_key_noop(self, sample_index):
        idx = delete_session(sample_index, "zzz")
        assert len(idx) == 2


# ---------------------------------------------------------------------------
# resolve_session_id
# ---------------------------------------------------------------------------

class TestResolveSessionId:
    def test_resolves_prefix(self, sample_index):
        assert resolve_session_id(sample_index, "aaa") == "aaa"

    def test_resolves_by_name(self, sample_index):
        assert resolve_session_id(sample_index, "aaaaa") == "aaa"

    def test_exits_on_no_match(self, sample_index):
        with pytest.raises(SystemExit):
            resolve_session_id(sample_index, "zzz")
