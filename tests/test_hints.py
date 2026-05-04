"""Tests for textsessions-hints consumer (Hint dataclass, hints module, indexer wiring, filters)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from textsessions.hints import read_hint
from textsessions.sessions import Hint, Lineage, Session, filter_sessions


def _s(**kw) -> Session:
    base = dict(
        id="a" * 32,
        name="abcde",
        profile="personal",
        last_active="2026-05-03 12:00",
        slug="something",
        repo_label="repo",
        repo_path=Path("/tmp/nope"),
    )
    base.update(kw)
    return Session(**base)


# --- Hint dataclass ---------------------------------------------------------

def test_hint_from_dict_none_or_empty_returns_none():
    assert Hint.from_dict(None) is None
    assert Hint.from_dict({}) is None
    # All-empty fields → None as well
    assert Hint.from_dict({"persona": "", "owner": "", "labels": []}) is None


def test_hint_from_dict_full():
    h = Hint.from_dict({
        "persona": "agentic-pivot",
        "owner": "pp:persona:agentic-pivot:run-7",
        "labels": ["pivot", "private"],
        "started": "2026-05-03T14:32:11Z",
    })
    assert h == Hint(
        persona="agentic-pivot",
        owner="pp:persona:agentic-pivot:run-7",
        labels=["pivot", "private"],
        started="2026-05-03T14:32:11Z",
    )


def test_hint_from_dict_coerces_label_types():
    """Labels are stringified; non-list labels are dropped."""
    h = Hint.from_dict({"persona": "p", "labels": [1, 2]})
    assert h.labels == ["1", "2"]
    h = Hint.from_dict({"persona": "p", "labels": "not-a-list"})
    assert h.labels == []


def test_hint_to_dict_round_trips():
    h = Hint(persona="p", owner="o", labels=["a", "b"], started="t")
    assert Hint.from_dict(h.to_dict()) == h


def test_hint_to_dict_omits_empty_fields():
    h = Hint(persona="p")
    assert h.to_dict() == {"persona": "p"}


# --- read_hint --------------------------------------------------------------

def test_read_hint_missing_returns_none(tmp_path):
    assert read_hint("does-not-exist", hint_dir=tmp_path) is None


def test_read_hint_empty_session_id_returns_none(tmp_path):
    assert read_hint("", hint_dir=tmp_path) is None


def test_read_hint_valid_yaml(tmp_path):
    sid = "abc123"
    (tmp_path / f"{sid}.yaml").write_text(yaml.safe_dump({"persona": "agentic-pivot"}))
    assert read_hint(sid, hint_dir=tmp_path) == {"persona": "agentic-pivot"}


def test_read_hint_malformed_yaml_returns_none(tmp_path):
    sid = "abc123"
    (tmp_path / f"{sid}.yaml").write_text("not: valid: yaml: at all: [")
    assert read_hint(sid, hint_dir=tmp_path) is None


def test_read_hint_non_dict_yaml_returns_none(tmp_path):
    sid = "abc123"
    (tmp_path / f"{sid}.yaml").write_text("- just\n- a\n- list\n")
    assert read_hint(sid, hint_dir=tmp_path) is None


# --- Session properties -----------------------------------------------------

def test_session_persona_default_empty():
    assert _s().persona == ""
    assert _s().labels == []


def test_session_persona_from_hint():
    s = _s(hint=Hint(persona="agentic-pivot", labels=["x"]))
    assert s.persona == "agentic-pivot"
    assert s.labels == ["x"]


def test_session_persona_chip_persona_only():
    s = _s(hint=Hint(persona="agentic-pivot"))
    # Brackets are escaped (`\[…]`) so Rich/Textual treat them as literal,
    # not as a markup tag. Critical when labels contain '-' or '#'.
    assert s.persona_chip == r"\[persona=agentic-pivot]"


def test_session_persona_chip_with_labels():
    s = _s(hint=Hint(persona="agentic-pivot", labels=["pivot", "private"]))
    assert s.persona_chip == r"\[persona=agentic-pivot, #pivot #private]"


def test_session_persona_chip_labels_only():
    s = _s(hint=Hint(labels=["wip"]))
    assert s.persona_chip == r"\[#wip]"


def test_persona_chip_renders_safely_through_rich():
    """Regression: persona_chip with hyphenated labels must not crash Rich's markup parser.

    Caught a TUI crash on 2026-05-03: rendering `[persona=foo, #pivot #private]` inside
    `[magenta]…[/magenta]` raised MarkupError because Rich saw `[persona=...]` as a tag.
    """
    from rich.console import Console
    from rich.text import Text
    s = _s(hint=Hint(persona="agentic-pivot", labels=["pivot", "private"]))
    # Wrap the chip in a styled markup span — exactly what tui/app.py does.
    markup = f"[magenta]{s.persona_chip}[/magenta]"
    # Should not raise.
    Text.from_markup(markup)
    # And the chip should round-trip plain (no leftover tags).
    assert "persona=agentic-pivot" in Text.from_markup(markup).plain


def test_session_persona_chip_empty_when_no_hint():
    assert _s().persona_chip == ""


# --- merged_owner precedence ------------------------------------------------

def test_merged_owner_hint_overrides_lineage():
    s = _s(
        lineage=Lineage(parent="personal", ephemeral=True, owner="lineage-owner"),
        hint=Hint(owner="hint-owner"),
    )
    assert s.merged_owner == "hint-owner"


def test_merged_owner_falls_back_to_lineage():
    s = _s(lineage=Lineage(parent="personal", owner="lineage-owner"), hint=Hint(persona="p"))
    assert s.merged_owner == "lineage-owner"


def test_merged_owner_empty_when_neither_set():
    assert _s().merged_owner == ""


# --- from_index_entry -------------------------------------------------------

def test_from_index_entry_with_hint(tmp_path):
    entry = {
        "name": "foo",
        "profile": "personal",
        "hint": {"persona": "agentic-pivot", "owner": "pp:run-7"},
    }
    s = Session.from_index_entry("sid1", entry, "repo", tmp_path)
    assert s.persona == "agentic-pivot"
    assert s.merged_owner == "pp:run-7"


def test_from_index_entry_no_hint(tmp_path):
    s = Session.from_index_entry("sid1", {"name": "foo", "profile": "personal"}, "repo", tmp_path)
    assert s.hint is None
    assert s.persona == ""


# --- filter_sessions: persona / label / owner -------------------------------

def test_filter_by_persona():
    a = _s(name="a", hint=Hint(persona="agentic-pivot"))
    b = _s(name="b", hint=Hint(persona="paperworlds-writer"))
    plain = _s(name="plain")
    out = filter_sessions([a, b, plain], persona="agentic-pivot")
    assert out == [a]


def test_filter_by_label():
    a = _s(name="a", hint=Hint(labels=["pivot", "private"]))
    b = _s(name="b", hint=Hint(labels=["public"]))
    plain = _s(name="plain")
    out = filter_sessions([a, b, plain], label="pivot")
    assert out == [a]


def test_filter_owner_matches_hint_or_lineage():
    """--owner should match merged owner: hint takes precedence, lineage is fallback."""
    via_hint = _s(name="hint", hint=Hint(owner="pp:run-7"))
    via_lineage = _s(name="lin", lineage=Lineage(parent="personal", owner="pp:run-7"))
    different = _s(name="x", hint=Hint(owner="other"))
    out = filter_sessions([via_hint, via_lineage, different], owner="pp:run-7")
    assert sorted(s.name for s in out) == ["hint", "lin"]


def test_filter_persona_excludes_no_hint():
    plain = _s(name="plain")
    out = filter_sessions([plain], persona="anything")
    assert out == []


# --- Indexer wiring ---------------------------------------------------------

def test_build_index_stores_hint_when_file_present(tmp_path, monkeypatch):
    """build_index reads ~/.cache/textsessions/hints/<sid>.yaml when present."""
    from textsessions import indexer

    fake_session = {
        "id": "abc123",
        "last_ts": "2026-05-03T12:00:00",
        "profile": ".claude-personal",
        "combined": "some work",
        "custom_title": "",
        "path": str(tmp_path / "abc123.jsonl"),
    }
    monkeypatch.setattr(indexer, "scan_sessions", lambda pairs: [fake_session])
    monkeypatch.setattr(indexer, "STATE_DIR", tmp_path)
    monkeypatch.setattr(indexer, "LEGACY_INDEX_DIR", tmp_path / "legacy")
    monkeypatch.setattr("textsessions.profiles.get_profile_lineage", lambda n: None)

    # Stub read_hint to return a payload for this session id only
    def fake_read_hint(sid: str, hint_dir=None):
        return {"persona": "agentic-pivot", "owner": "pp:run-7"} if sid == "abc123" else None

    monkeypatch.setattr("textsessions.hints.read_hint", fake_read_hint)

    new_index = indexer.build_index("test-key", ["dummy"])
    assert new_index["abc123"]["hint"] == {
        "persona": "agentic-pivot",
        "owner": "pp:run-7",
    }


def test_build_index_no_hint_when_file_absent(tmp_path, monkeypatch):
    from textsessions import indexer

    fake_session = {
        "id": "abc123", "last_ts": "2026-05-03T12:00:00",
        "profile": ".claude-personal", "combined": "x", "custom_title": "",
        "path": str(tmp_path / "x.jsonl"),
    }
    monkeypatch.setattr(indexer, "scan_sessions", lambda pairs: [fake_session])
    monkeypatch.setattr(indexer, "STATE_DIR", tmp_path)
    monkeypatch.setattr(indexer, "LEGACY_INDEX_DIR", tmp_path / "legacy")
    monkeypatch.setattr("textsessions.profiles.get_profile_lineage", lambda n: None)
    monkeypatch.setattr("textsessions.hints.read_hint", lambda sid, hint_dir=None: None)

    new_index = indexer.build_index("test-key", ["dummy"])
    assert "hint" not in new_index["abc123"]


def test_build_index_preserves_hint_when_file_disappears(tmp_path, monkeypatch):
    """If the hint file is gone (e.g. cache cleared), fall back to old index entry."""
    from textsessions import indexer

    fake_session = {
        "id": "abc123", "last_ts": "2026-05-03T12:00:00",
        "profile": ".claude-personal", "combined": "x", "custom_title": "",
        "path": str(tmp_path / "x.jsonl"),
    }
    monkeypatch.setattr(indexer, "scan_sessions", lambda pairs: [fake_session])
    monkeypatch.setattr(indexer, "STATE_DIR", tmp_path)
    monkeypatch.setattr(indexer, "LEGACY_INDEX_DIR", tmp_path / "legacy")

    (tmp_path / "test-key.yaml").write_text(yaml.safe_dump({
        "abc123": {
            "name": "abc12", "profile": "personal", "last_active": "2026-05-02 10:00",
            "slug": "old", "hint": {"persona": "agentic-pivot", "owner": "pp:run-old"},
        },
    }))

    monkeypatch.setattr("textsessions.profiles.get_profile_lineage", lambda n: None)
    monkeypatch.setattr("textsessions.hints.read_hint", lambda sid, hint_dir=None: None)

    new_index = indexer.build_index("test-key", ["dummy"])
    assert new_index["abc123"]["hint"] == {
        "persona": "agentic-pivot",
        "owner": "pp:run-old",
    }
