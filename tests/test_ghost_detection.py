"""Tests for ghost/orphan session detection."""

from __future__ import annotations

from pathlib import Path

import pytest

from textsessions.sessions import Session


def make_session(
    sid: str = "a" * 32,
    name: str = "a1b2c",
    slug: str = "hello there",
    tags: list[str] | None = None,
    priority: str = "",
    repo_path: Path | None = None,
) -> Session:
    return Session(
        id=sid,
        name=name,
        profile="personal",
        last_active="2026-04-07 12:00",
        slug=slug,
        tags=tags or [],
        priority=priority,
        repo_label="test",
        repo_path=repo_path or Path("/nonexistent/path"),
    )


class TestIsGhost:
    def test_nonexistent_repo_is_ghost(self, tmp_path):
        s = make_session(repo_path=Path("/nonexistent/definitely/not/here"))
        assert s.is_ghost is True

    def test_dir_without_git_is_ghost(self, tmp_path):
        s = make_session(repo_path=tmp_path)
        assert s.is_ghost is True

    def test_valid_git_repo_is_not_ghost(self, tmp_path):
        (tmp_path / ".git").mkdir()
        s = make_session(repo_path=tmp_path)
        assert s.is_ghost is False


class TestIsOrphan:
    def test_short_name_no_metadata_short_slug_is_orphan(self):
        s = make_session(name="a1b2c", slug="hello there", tags=[], priority="")
        assert s.is_orphan is True

    def test_has_tags_not_orphan(self):
        s = make_session(name="a1b2c", slug="hello there", tags=["daily"])
        assert s.is_orphan is False

    def test_has_priority_not_orphan(self):
        s = make_session(name="a1b2c", slug="hello there", priority="1")
        assert s.is_orphan is False

    def test_long_name_not_orphan(self):
        s = make_session(name="my-real-feature-work", slug="hello there")
        assert s.is_orphan is False

    def test_name_with_spaces_not_orphan(self):
        s = make_session(name="fix bug", slug="hello there")
        assert s.is_orphan is False

    def test_long_slug_not_orphan(self):
        s = make_session(name="a1b2c", slug="implement the new authentication flow with oauth2 tokens and refresh")
        assert s.is_orphan is False

    def test_exactly_8_word_slug_is_orphan(self):
        s = make_session(name="a1b2c", slug="one two three four five six seven eight")
        assert s.is_orphan is True

    def test_nine_word_slug_not_orphan(self):
        s = make_session(name="a1b2c", slug="one two three four five six seven eight nine")
        assert s.is_orphan is False


class TestIsArchived:
    def test_archived_tag_detected(self):
        s = make_session(tags=["archived"])
        assert s.is_archived is True

    def test_no_archived_tag(self):
        s = make_session(tags=["daily"])
        assert s.is_archived is False

    def test_empty_tags(self):
        s = make_session(tags=[])
        assert s.is_archived is False
