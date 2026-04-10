"""Tests for filter_sessions tag and text filtering."""

from __future__ import annotations

from pathlib import Path

from textsessions.sessions import Session, filter_sessions


def _s(sid: str, name: str, tags: list[str] = [], slug: str = "", description: str = "") -> Session:
    return Session(
        id=sid, name=name, profile="default",
        last_active="2026-01-01 10:00",
        slug=slug or name,
        tags=tags,
        description=description,
        repo_path=Path("/tmp/fake"),
    )


SESSIONS = [
    _s("a", "auth-work",    tags=["auth", "api"],  description="Auth refactor"),
    _s("b", "deploy-thing", tags=["api"],           description="Deploy pipeline"),
    _s("c", "misc-task",    tags=["infra"],         description="Some infra work"),
    _s("d", "auth-two",     tags=["auth"],          description="Auth v2"),
]


def test_hash_tag_filter_single():
    result = filter_sessions(SESSIONS, query="#auth")
    assert {s.id for s in result} == {"a", "d"}


def test_hash_tag_filter_multiple_and():
    # Must have both tags
    result = filter_sessions(SESSIONS, query="#auth #api")
    assert {s.id for s in result} == {"a"}


def test_hash_tag_no_match():
    result = filter_sessions(SESSIONS, query="#nonexistent")
    assert result == []


def test_hash_tag_combined_with_text():
    # #auth AND text "v2"
    result = filter_sessions(SESSIONS, query="#auth v2")
    assert {s.id for s in result} == {"d"}


def test_text_only_unchanged():
    result = filter_sessions(SESSIONS, query="auth")
    assert {s.id for s in result} == {"a", "d"}
