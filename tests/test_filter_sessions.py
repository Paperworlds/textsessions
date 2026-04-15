"""Tests for filter_sessions tag and text filtering."""

from __future__ import annotations

from textsessions.sessions import Session, filter_sessions

from conftest import make_session


SESSIONS = [
    make_session("a", "auth-work",    tags=["auth", "api"],  slug="auth-work",    description="Auth refactor"),
    make_session("b", "deploy-thing", tags=["api"],           slug="deploy-thing", description="Deploy pipeline"),
    make_session("c", "misc-task",    tags=["infra"],         slug="misc-task",    description="Some infra work"),
    make_session("d", "auth-two",     tags=["auth"],          slug="auth-two",     description="Auth v2"),
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
