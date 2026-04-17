"""Unit tests for textsessions.indexer."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

def importable(name: str) -> bool:
    try:
        __import__(name)
        return True
    except ImportError:
        return False


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


def test_scan_sessions_launch_name_fallback(tmp_path):
    """--name from launch metadata is used when no custom-title in .jsonl."""
    claude_dir = tmp_path / ".claude-work"
    claude_dir.mkdir()
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()

    sid = "c895c641-ab6b-46bf-9d43-447a7ef8dd8e"
    lines = [
        json.dumps({"type": "user", "timestamp": "2026-04-11T21:00:00Z",
                    "message": {"content": "Help me build a daemon"}}),
    ]
    (sessions_dir / f"{sid}.jsonl").write_text("\n".join(lines))

    # Write PID metadata with session name
    meta_dir = claude_dir / "sessions"
    meta_dir.mkdir()
    (meta_dir / "12345.json").write_text(json.dumps({
        "pid": 12345,
        "sessionId": sid,
        "name": "daemon",
    }))

    results = scan_sessions([f"{claude_dir}::{sessions_dir}"])
    assert len(results) == 1
    assert results[0]["custom_title"] == "daemon"


def test_scan_sessions_custom_title_overrides_launch_name(tmp_path):
    """custom-title in .jsonl takes precedence over --name from metadata."""
    claude_dir = tmp_path / ".claude-work"
    claude_dir.mkdir()
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()

    sid = "abcd1234-0000-0000-0000-000000000000"
    lines = [
        json.dumps({"type": "custom-title", "customTitle": "renamed-title",
                    "timestamp": "2026-04-11T21:00:00Z"}),
        json.dumps({"type": "user", "timestamp": "2026-04-11T21:00:01Z",
                    "message": {"content": "Hello"}}),
    ]
    (sessions_dir / f"{sid}.jsonl").write_text("\n".join(lines))

    meta_dir = claude_dir / "sessions"
    meta_dir.mkdir()
    (meta_dir / "99999.json").write_text(json.dumps({
        "pid": 99999,
        "sessionId": sid,
        "name": "original-launch-name",
    }))

    results = scan_sessions([f"{claude_dir}::{sessions_dir}"])
    assert len(results) == 1
    assert results[0]["custom_title"] == "renamed-title"


@pytest.mark.skipif(
    not importable("tomli_w"),
    reason="tomli_w not installed (needed by config → sessions chain)",
)
def test_reindex_repos_includes_subdirectories(tmp_path):
    """Sessions from repo subdirs (e.g. features/branch) are included."""
    from textsessions.indexer import reindex_repos

    claude_dir = tmp_path / ".claude-personal"
    claude_dir.mkdir()

    repo_path = tmp_path / "myrepo"
    repo_path.mkdir()

    # Main repo sessions dir
    rk = str(repo_path).replace("/", "-")
    main_dir = claude_dir / "projects" / rk
    main_dir.mkdir(parents=True)
    sid1 = "a" * 36
    (main_dir / f"{sid1}.jsonl").write_text(
        json.dumps({"type": "user", "timestamp": "2026-01-01T10:00:00Z",
                    "message": {"content": "Main repo session"}}) + "\n"
    )

    # Subdirectory sessions dir (features/branch)
    sub_key = rk + "-features-my-branch"
    sub_dir = claude_dir / "projects" / sub_key
    sub_dir.mkdir(parents=True)
    sid2 = "b" * 36
    (sub_dir / f"{sid2}.jsonl").write_text(
        json.dumps({"type": "user", "timestamp": "2026-01-02T10:00:00Z",
                    "message": {"content": "Feature branch session"}}) + "\n"
    )

    state_dir = tmp_path / "state"

    # Use a simple namespace to avoid importing RepoConfig (which pulls tomli_w)
    class FakeRepo:
        def __init__(self, path, label, profile):
            self.path = path
            self.label = label
            self.profile = profile

    repo = FakeRepo(path=repo_path, label="myrepo", profile="personal")

    with patch("textsessions.indexer.STATE_DIR", state_dir), \
         patch("textsessions.indexer.LEGACY_INDEX_DIR", tmp_path / "legacy"):
        total = reindex_repos([repo], [claude_dir])

    assert total == 2


@pytest.mark.skipif(
    not importable("tomli_w"),
    reason="tomli_w not installed (needed by config → sessions chain)",
)
def test_reindex_repos_excludes_child_repo_sessions(tmp_path):
    """Subdir matching must not claim sessions belonging to another configured repo."""
    from textsessions.indexer import reindex_repos

    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()

    parent_path = tmp_path / "projects" / "personal"
    parent_path.mkdir(parents=True)
    child_path = parent_path / "paperworlds" / "paperagents"
    child_path.mkdir(parents=True)

    parent_rk = str(parent_path).replace("/", "-")
    child_rk = str(child_path).replace("/", "-")

    # Parent repo session
    parent_dir = claude_dir / "projects" / parent_rk
    parent_dir.mkdir(parents=True)
    (parent_dir / ("a" * 36 + ".jsonl")).write_text(
        json.dumps({"type": "user", "timestamp": "2026-01-01T10:00:00Z",
                    "message": {"content": "Parent session"}}) + "\n"
    )

    # Child repo session (key starts with parent key, but is a separate repo)
    child_dir = claude_dir / "projects" / child_rk
    child_dir.mkdir(parents=True)
    (child_dir / ("b" * 36 + ".jsonl")).write_text(
        json.dumps({"type": "user", "timestamp": "2026-01-02T10:00:00Z",
                    "message": {"content": "Child session"}}) + "\n"
    )

    class FakeRepo:
        def __init__(self, path, label, profile):
            self.path = path
            self.label = label
            self.profile = profile

    parent_repo = FakeRepo(path=parent_path, label="personal", profile="personal")
    child_repo = FakeRepo(path=child_path, label="paperagents", profile="personal")

    state_dir = tmp_path / "state"
    with patch("textsessions.indexer.STATE_DIR", state_dir), \
         patch("textsessions.indexer.LEGACY_INDEX_DIR", tmp_path / "legacy"):
        reindex_repos([parent_repo, child_repo], [claude_dir])
        parent_index = load_index(parent_rk)
        child_index = load_index(child_rk)

    # Each repo gets exactly its own session — parent must NOT absorb child's
    assert len(parent_index) == 1
    assert "a" * 36 in parent_index
    assert len(child_index) == 1
    assert "b" * 36 in child_index


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


def test_build_index_name_follows_latest_custom_title(tmp_path):
    """Name always derives from custom_title, even if old index had a different name."""
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
    # Pre-seed with an old name from a previous custom_title
    existing = {sid: {"name": "old-auth-name", "profile": "default", "last_active": "2026-01-01 10:00", "slug": "old"}}
    (state_dir / "test-repo.yaml").write_text(yaml.safe_dump(existing))
    pairs = [f"{claude_dir}::{sessions_dir}"]
    with patch("textsessions.indexer.STATE_DIR", state_dir), \
         patch("textsessions.indexer.LEGACY_INDEX_DIR", tmp_path / "legacy"):
        index = build_index("test-repo", pairs)
    # custom_title is authoritative — name must derive from it
    assert "auth" in index[sid]["name"].lower()
    assert index[sid]["description"] == "Auth refactor for login flow"


def test_build_index_preserves_name_without_custom_title(tmp_path):
    """Without custom_title, old user-set name is preserved across reindexes."""
    claude_dir = tmp_path / ".claude"
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    sid = "ab12cd" + "0" * 26
    lines = [
        json.dumps({"type": "user", "timestamp": "2026-01-01T10:00:00Z",
                    "message": {"content": "Help me with auth"}}),
    ]
    (sessions_dir / f"{sid}.jsonl").write_text("\n".join(lines))
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    existing = {sid: {"name": "my-auth-work", "profile": "default", "last_active": "2026-01-01 10:00", "slug": "old"}}
    (state_dir / "test-repo.yaml").write_text(yaml.safe_dump(existing))
    pairs = [f"{claude_dir}::{sessions_dir}"]
    with patch("textsessions.indexer.STATE_DIR", state_dir), \
         patch("textsessions.indexer.LEGACY_INDEX_DIR", tmp_path / "legacy"):
        index = build_index("test-repo", pairs)
    # No custom_title → old name preserved
    assert index[sid]["name"] == "my-auth-work"


def test_build_index_updates_name_when_custom_title_changes(tmp_path):
    """Regression: when custom_title changes between reindexes, name must update."""
    claude_dir = tmp_path / ".claude"
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    sid = "ab12cd" + "0" * 26
    state_dir = tmp_path / "state"

    # First index: custom_title is "ts"
    lines = [
        json.dumps({"type": "user", "timestamp": "2026-01-01T10:00:00Z",
                    "message": {"content": "Help me with textsessions"}}),
        json.dumps({"type": "custom-title", "timestamp": "2026-01-01T10:01:00Z",
                    "customTitle": "ts"}),
    ]
    (sessions_dir / f"{sid}.jsonl").write_text("\n".join(lines))
    pairs = [f"{claude_dir}::{sessions_dir}"]
    with patch("textsessions.indexer.STATE_DIR", state_dir), \
         patch("textsessions.indexer.LEGACY_INDEX_DIR", tmp_path / "legacy"):
        index1 = build_index("test-repo", pairs)
    assert index1[sid]["name"] == "ts"

    # Now custom_title changes to "sessions" (user did /rename in Claude)
    lines.append(json.dumps({"type": "custom-title", "timestamp": "2026-01-01T10:02:00Z",
                             "customTitle": "sessions"}))
    (sessions_dir / f"{sid}.jsonl").write_text("\n".join(lines))
    with patch("textsessions.indexer.STATE_DIR", state_dir), \
         patch("textsessions.indexer.LEGACY_INDEX_DIR", tmp_path / "legacy"):
        index2 = build_index("test-repo", pairs)
    # Name must update to match the new custom_title, not stay as old "ts"
    assert index2[sid]["name"] == "sessions"
    assert index2[sid]["description"] == "sessions"


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

    def test_appends_custom_title_via_jsonl_path(self, sample_index, tmp_path):
        """Rename uses jsonl_path stored in index to write custom-title (fast path)."""
        jsonl = tmp_path / "aaa.jsonl"
        jsonl.write_text("")
        sample_index["aaa"]["jsonl_path"] = str(jsonl)

        do_rename(sample_index, "aaa", "Persist This Name", repo_key="-Users-projects-foo")

        lines = [json.loads(l) for l in jsonl.read_text().splitlines()]
        assert any(l.get("type") == "custom-title" and l.get("customTitle") == "Persist This Name" for l in lines)

    def test_appends_custom_title_fallback_search(self, sample_index, tmp_path):
        """Rename falls back to searching ~/.claude* when jsonl_path is absent (e.g. subdir session)."""
        repo_key = "-Users-projects-foo"
        sid = "aaa"
        # Simulate session stored under a subdirectory of the repo
        subdir_key = repo_key + "-src-feature"
        jsonl = tmp_path / ".claude" / "projects" / subdir_key / f"{sid}.jsonl"
        jsonl.parent.mkdir(parents=True)
        jsonl.write_text("")
        # No jsonl_path in index entry — forces the fallback search path

        with patch("textsessions.indexer.Path.home", return_value=tmp_path):
            do_rename(sample_index, sid, "Persist This Name", repo_key=repo_key)

        lines = [json.loads(l) for l in jsonl.read_text().splitlines()]
        assert any(l.get("type") == "custom-title" and l.get("customTitle") == "Persist This Name" for l in lines)

    def test_updates_launch_metadata_pid_json(self, sample_index, tmp_path):
        """Rename also updates ~/.claude*/sessions/<pid>.json so Claude Code stops
        re-asserting the old launch --name on every turn.

        Regression: presync → pathfinder-upgrade kept reverting because Claude
        Code writes custom-title: <launch-name> on each resume/turn.
        """
        sid = "aaa"
        jsonl = tmp_path / f"{sid}.jsonl"
        jsonl.write_text("")
        sample_index[sid]["jsonl_path"] = str(jsonl)

        meta_dir = tmp_path / ".claude" / "sessions"
        meta_dir.mkdir(parents=True)
        pid_file = meta_dir / "12345.json"
        pid_file.write_text(json.dumps({"pid": 12345, "sessionId": sid, "name": "presync"}))

        with patch("textsessions.indexer.Path.home", return_value=tmp_path):
            do_rename(sample_index, sid, "pathfinder-upgrade", repo_key="-Users-projects-foo")

        updated = json.loads(pid_file.read_text())
        assert updated["name"] == "pathfinder-upgrade"
        assert updated["sessionId"] == sid  # sanity — didn't corrupt the file

    def test_does_not_touch_other_sessions_pid_json(self, sample_index, tmp_path):
        """Only the matching sessionId's PID json gets updated."""
        sid = "aaa"
        jsonl = tmp_path / f"{sid}.jsonl"
        jsonl.write_text("")
        sample_index[sid]["jsonl_path"] = str(jsonl)

        meta_dir = tmp_path / ".claude" / "sessions"
        meta_dir.mkdir(parents=True)
        (meta_dir / "12345.json").write_text(json.dumps({"pid": 12345, "sessionId": sid, "name": "old"}))
        other_pid = meta_dir / "99999.json"
        other_pid.write_text(json.dumps({"pid": 99999, "sessionId": "other-sid", "name": "untouched"}))

        with patch("textsessions.indexer.Path.home", return_value=tmp_path):
            do_rename(sample_index, sid, "renamed", repo_key="-Users-projects-foo")

        other = json.loads(other_pid.read_text())
        assert other["name"] == "untouched"

    def test_updates_pid_json_across_multiple_claude_dirs(self, sample_index, tmp_path):
        """Launch metadata can live in .claude, .claude-work, .claude-personal etc."""
        sid = "aaa"
        jsonl = tmp_path / f"{sid}.jsonl"
        jsonl.write_text("")
        sample_index[sid]["jsonl_path"] = str(jsonl)

        for subdir in (".claude-work", ".claude-personal"):
            meta_dir = tmp_path / subdir / "sessions"
            meta_dir.mkdir(parents=True)
            (meta_dir / "1.json").write_text(
                json.dumps({"sessionId": sid, "name": "stale-launch-name"})
            )

        with patch("textsessions.indexer.Path.home", return_value=tmp_path):
            do_rename(sample_index, sid, "renamed", repo_key="-Users-projects-foo")

        for subdir in (".claude-work", ".claude-personal"):
            pid_file = tmp_path / subdir / "sessions" / "1.json"
            assert json.loads(pid_file.read_text())["name"] == "renamed"

    def test_skips_malformed_pid_json_gracefully(self, sample_index, tmp_path):
        """Malformed PID json must not crash rename; valid ones still update."""
        sid = "aaa"
        jsonl = tmp_path / f"{sid}.jsonl"
        jsonl.write_text("")
        sample_index[sid]["jsonl_path"] = str(jsonl)

        meta_dir = tmp_path / ".claude" / "sessions"
        meta_dir.mkdir(parents=True)
        (meta_dir / "broken.json").write_text("{not valid json")
        good = meta_dir / "good.json"
        good.write_text(json.dumps({"sessionId": sid, "name": "old"}))

        with patch("textsessions.indexer.Path.home", return_value=tmp_path):
            do_rename(sample_index, sid, "renamed", repo_key="-Users-projects-foo")

        assert json.loads(good.read_text())["name"] == "renamed"

    def test_rename_survives_simulated_claude_rewrite(self, sample_index, tmp_path):
        """Regression: after rename, if Claude Code writes a fresh custom-title
        matching the (now-updated) launch name, the rename must survive.

        Before the fix, launch name stayed as 'presync' and the re-asserted
        custom-title reverted the rename. After the fix, launch name matches
        the new title so re-asserts are idempotent.
        """
        from textsessions.indexer import build_index

        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        sessions_dir = claude_dir / "projects" / "test-repo"
        sessions_dir.mkdir(parents=True)

        sid = "ab12cd34" + "0" * 28
        jsonl = sessions_dir / f"{sid}.jsonl"
        jsonl.write_text("\n".join([
            json.dumps({"type": "user", "timestamp": "2026-04-17T10:00:00Z",
                        "message": {"content": "Help me debug"}}),
            json.dumps({"type": "custom-title", "timestamp": "2026-04-17T10:00:01Z",
                        "customTitle": "presync"}),
        ]) + "\n")

        meta_dir = claude_dir / "sessions"
        meta_dir.mkdir()
        pid_file = meta_dir / "12345.json"
        pid_file.write_text(json.dumps({"pid": 12345, "sessionId": sid, "name": "presync"}))

        state_dir = tmp_path / "state"
        pairs = [f"{claude_dir}::{sessions_dir}"]

        with patch("textsessions.indexer.STATE_DIR", state_dir), \
             patch("textsessions.indexer.LEGACY_INDEX_DIR", tmp_path / "legacy"):
            index = build_index("test-repo", pairs)
            assert index[sid]["name"] == "presync"

            # User renames via TUI
            with patch("textsessions.indexer.Path.home", return_value=tmp_path):
                do_rename(index, sid, "pathfinder-upgrade", repo_key="test-repo")
            save_index("test-repo", index)

            # Simulate Claude Code writing a fresh custom-title on next turn —
            # it reads the PID json's name and echoes it into the jsonl.
            launch_name = json.loads(pid_file.read_text())["name"]
            with open(jsonl, "a") as f:
                f.write(json.dumps({
                    "type": "custom-title",
                    "timestamp": "2026-04-17T11:00:00Z",
                    "customTitle": launch_name,
                }) + "\n")

            rebuilt = build_index("test-repo", pairs)

        # The rename must survive Claude's re-assertion on next turn.
        assert rebuilt[sid]["name"] == "pathfinder-upgrade"
        assert rebuilt[sid]["description"] == "pathfinder-upgrade"


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
