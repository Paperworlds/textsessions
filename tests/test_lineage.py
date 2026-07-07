"""Tests for shallow-clone lineage surface (Lineage dataclass, filters, indexer)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from textsessions.sessions import Lineage, Session, filter_sessions


def _s(**kw) -> Session:
    """Build a Session with sensible defaults; override anything via kwargs."""
    base = dict(
        id="a" * 32,
        name="abcde",
        profile="work",
        last_active="2026-04-27 12:00",
        slug="something",
        repo_label="repo",
        repo_path=Path("/tmp/nope"),
    )
    base.update(kw)
    return Session(**base)


# --- Lineage dataclass ------------------------------------------------------

def test_lineage_from_dict_none_returns_none():
    assert Lineage.from_dict(None) is None
    assert Lineage.from_dict({}) is None


def test_lineage_from_dict_full():
    l = Lineage.from_dict({"parent": "personal", "ephemeral": True, "owner": "run-42"})
    assert l == Lineage(parent="personal", ephemeral=True, owner="run-42")


def test_lineage_to_dict_omits_empty_owner():
    l = Lineage(parent="work", ephemeral=False, owner="")
    assert l.to_dict() == {"parent": "work", "ephemeral": False}


def test_lineage_to_dict_includes_owner_when_set():
    l = Lineage(parent="work", ephemeral=True, owner="textprompts:run-42")
    assert l.to_dict() == {"parent": "work", "ephemeral": True, "owner": "textprompts:run-42"}


# --- Session classmethod + properties --------------------------------------

def test_session_from_index_entry_no_lineage():
    s = Session.from_index_entry("sid1", {"name": "foo", "profile": "work"}, "repo", Path("/tmp"))
    assert s.lineage is None
    assert s.is_shallow is False
    assert s.lineage_chip == ""


def test_session_from_index_entry_with_lineage():
    entry = {
        "name": "foo",
        "profile": "scratch-1",
        "lineage": {"parent": "personal", "ephemeral": True, "owner": "pp:run-1"},
    }
    s = Session.from_index_entry("sid1", entry, "repo", Path("/tmp"))
    assert s.is_shallow is True
    assert s.lineage_chip == r"\[shallow ← personal, ephemeral, owner=pp:run-1]"


def test_lineage_chip_non_ephemeral():
    s = _s(lineage=Lineage(parent="personal", ephemeral=False, owner=""))
    assert s.lineage_chip == r"\[shallow ← personal]"


def test_lineage_chip_ephemeral_no_owner():
    s = _s(lineage=Lineage(parent="work", ephemeral=True, owner=""))
    assert s.lineage_chip == r"\[shallow ← work, ephemeral]"


# --- filter_sessions new options -------------------------------------------

def _shallow(parent: str, owner: str = "") -> Session:
    return _s(profile=f"clone-of-{parent}", lineage=Lineage(parent=parent, ephemeral=bool(owner), owner=owner))


def test_filter_shallow_only():
    plain = _s(name="plain")
    shallow = _shallow("personal")
    out = filter_sessions([plain, shallow], shallow_only=True)
    assert out == [shallow]


def test_filter_no_shallow():
    plain = _s(name="plain")
    shallow = _shallow("personal")
    out = filter_sessions([plain, shallow], no_shallow=True)
    assert out == [plain]


def test_filter_by_parent():
    a = _shallow("personal")
    b = _shallow("work")
    out = filter_sessions([a, b], parent="personal")
    assert out == [a]


def test_filter_by_owner():
    a = _shallow("personal", owner="run-1")
    b = _shallow("personal", owner="run-2")
    plain = _s(name="plain")
    out = filter_sessions([a, b, plain], owner="run-2")
    assert out == [b]


def test_filter_owner_excludes_non_shallow():
    """parent/owner filters must require lineage — non-shallow can't match."""
    plain = _s(name="plain")
    out = filter_sessions([plain], parent="anything")
    assert out == []
    out = filter_sessions([plain], owner="anything")
    assert out == []


# --- Indexer wiring --------------------------------------------------------

def test_build_index_stores_lineage_when_shallow(tmp_path, monkeypatch):
    """build_index queries get_profile_lineage and stores lineage block on shallow profiles."""
    from textsessions import indexer

    # Stub scan_sessions to return one fake session bypassing .jsonl reading.
    fake_session = {
        "id": "abc123",
        "last_ts": "2026-04-27T12:00:00",
        "profile": ".claude-scratch-1",  # build_index strips ".claude-" prefix
        "combined": "do the thing",
        "custom_title": "",
        "path": str(tmp_path / "abc123.jsonl"),
    }
    monkeypatch.setattr(indexer, "scan_sessions", lambda pairs: [fake_session])

    # Stub state dir to avoid hitting real ~/.local
    monkeypatch.setattr(indexer, "STATE_DIR", tmp_path)
    # write_legacy_tsv touches LEGACY_INDEX_DIR — point it at tmp too
    monkeypatch.setattr(indexer, "LEGACY_INDEX_DIR", tmp_path / "legacy")

    # Stub profiles.get_profile_lineage to return a shallow record for "scratch-1"
    def fake_lineage(name: str) -> dict | None:
        if name == "scratch-1":
            return {"shallow": True, "parent": "work", "ephemeral": True, "owner": "pp:run-7"}
        return None

    monkeypatch.setattr("textsessions.profiles.get_profile_lineage", fake_lineage)

    new_index = indexer.build_index("test-key", ["dummy"])
    assert "abc123" in new_index
    entry = new_index["abc123"]
    assert entry["lineage"] == {"parent": "work", "ephemeral": True, "owner": "pp:run-7"}


def test_build_index_no_lineage_for_normal_profile(tmp_path, monkeypatch):
    from textsessions import indexer

    fake_session = {
        "id": "abc123", "last_ts": "2026-04-27T12:00:00",
        "profile": ".claude-work", "combined": "x", "custom_title": "", "path": str(tmp_path / "x.jsonl"),
    }
    monkeypatch.setattr(indexer, "scan_sessions", lambda pairs: [fake_session])
    monkeypatch.setattr(indexer, "STATE_DIR", tmp_path)
    monkeypatch.setattr(indexer, "LEGACY_INDEX_DIR", tmp_path / "legacy")
    monkeypatch.setattr("textsessions.profiles.get_profile_lineage", lambda n: None)

    new_index = indexer.build_index("test-key", ["dummy"])
    assert "lineage" not in new_index["abc123"]


def test_build_index_preserves_lineage_when_profile_gone(tmp_path, monkeypatch):
    """If the profile was GCd, fall back to the previous index's lineage record."""
    from textsessions import indexer

    fake_session = {
        "id": "abc123", "last_ts": "2026-04-27T12:00:00",
        "profile": ".claude-scratch-1", "combined": "x", "custom_title": "", "path": str(tmp_path / "x.jsonl"),
    }
    monkeypatch.setattr(indexer, "scan_sessions", lambda pairs: [fake_session])
    monkeypatch.setattr(indexer, "STATE_DIR", tmp_path)
    monkeypatch.setattr(indexer, "LEGACY_INDEX_DIR", tmp_path / "legacy")

    # Pre-populate the YAML index with a prior lineage record.
    import yaml
    (tmp_path / "test-key.yaml").write_text(yaml.safe_dump({
        "abc123": {
            "name": "abc12", "profile": "scratch-1", "last_active": "2026-04-26 10:00",
            "slug": "old", "lineage": {"parent": "personal", "ephemeral": True, "owner": "pp:run-old"},
        },
    }))

    # textaccounts no longer knows about scratch-1 (profile was GCd)
    monkeypatch.setattr("textsessions.profiles.get_profile_lineage", lambda n: None)

    new_index = indexer.build_index("test-key", ["dummy"])
    assert new_index["abc123"]["lineage"] == {
        "parent": "personal", "ephemeral": True, "owner": "pp:run-old",
    }


# --- profiles.py gateway --------------------------------------------------

def test_get_profile_lineage_empty_name():
    from textsessions.profiles import get_profile_lineage
    assert get_profile_lineage("") is None


def test_get_profile_lineage_swallows_exceptions(monkeypatch):
    from textsessions import profiles
    monkeypatch.setattr(profiles, "_ta_get_profile_lineage", lambda n: (_ for _ in ()).throw(RuntimeError("oops")))
    assert profiles.get_profile_lineage("anything") is None
