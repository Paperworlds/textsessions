"""Tests for ghost/orphan session detection."""

from __future__ import annotations

from pathlib import Path

import pytest

from textsessions.sessions import Session

from conftest import make_session


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
    def test_hex_hash_name_no_metadata_is_orphan(self):
        s = make_session(name="c5796", tags=[], priority="")
        assert s.is_orphan is True

    def test_hex_hash_8chars_is_orphan(self):
        s = make_session(name="ac4b7f3e", tags=[], priority="")
        assert s.is_orphan is True

    def test_hex_hash_tagged_not_orphan(self):
        s = make_session(name="ac4b7", tags=["daily"])
        assert s.is_orphan is False

    def test_hex_hash_with_priority_not_orphan(self):
        s = make_session(name="f68e2", priority="1")
        assert s.is_orphan is False

    def test_short_meaningful_name_not_orphan(self):
        s = make_session(name="pp")
        assert s.is_orphan is False

    def test_hyphenated_name_not_orphan(self):
        s = make_session(name="ws-internal")
        assert s.is_orphan is False

    def test_another_hyphenated_name_not_orphan(self):
        s = make_session(name="prdx-admin")
        assert s.is_orphan is False

    def test_long_slug_hex_name_is_orphan(self):
        # Slug length no longer matters — only the name pattern
        s = make_session(name="c5796", slug="hello sir | how much context did i use this far?")
        assert s.is_orphan is True

    def test_hex_too_short_not_orphan(self):
        s = make_session(name="a1b2")  # 4 chars — below threshold
        assert s.is_orphan is False

    def test_hex_too_long_not_orphan(self):
        s = make_session(name="a1b2c3d4e")  # 9 chars — above threshold
        assert s.is_orphan is False

    def test_non_hex_short_name_not_orphan(self):
        s = make_session(name="gx7z9")  # contains g, z — not hex
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
