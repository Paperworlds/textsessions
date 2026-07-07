"""Tests for `textsessions migrate` CLI command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from textsessions.cli import main
from textsessions.config import Config, RepoConfig
from textsessions.sessions import Session


def _cfg() -> Config:
    return Config(repos=[
        RepoConfig(path=Path("/projects/textread"), label="textread", profile="personal"),
    ])


def _session(**kw) -> Session:
    base = dict(
        id="a" * 32,
        name="my-session",
        profile="work",
        last_active="2026-06-30 10:00",
        slug="some session",
        repo_label="textread",
        repo_path=Path("/projects/textread"),
    )
    base.update(kw)
    return Session(**base)


def _invoke(args, sessions, *, index_entry=None, src_exists=True, copy_ok=True):
    sid = sessions[0].id if sessions else "a" * 32
    index = {sid: {"jsonl_path": f"/home/user/.claude/projects/repo/{sid}.jsonl", **(index_entry or {})}}

    # lazy imports in migrate_cmd → patch at their source modules
    with patch("textsessions.cli.load", return_value=_cfg()), \
         patch("textsessions.cli.load_sessions", return_value=sessions), \
         patch("textsessions.profiles.validate_explicit_profile"), \
         patch("textsessions.profiles.env_for_profile", return_value={"CLAUDE_CONFIG_DIR": "/home/user/.claude-personal"}), \
         patch("textsessions.indexer.load_index", return_value=index), \
         patch("textsessions.config.detect_claude_dirs", return_value=[]), \
         patch("textsessions.indexer.reindex_repos", return_value=1), \
         patch("pathlib.Path.exists", return_value=src_exists), \
         patch("pathlib.Path.mkdir"), \
         patch("textsessions.cli.shutil.copy2") as copy_mock:
        result = CliRunner().invoke(main, ["migrate", *args])
    return result, copy_mock


# --- happy path ---

def test_migrate_copies_jsonl(tmp_path):
    """migrate copies the source .jsonl to the target profile's project dir."""
    s = _session()
    result, copy_mock = _invoke(["my-session", "--to", "personal"], [s])
    assert result.exit_code == 0, result.output
    assert copy_mock.called
    assert "copied" in result.output


def test_migrate_prints_resume_instructions():
    """migrate prints eval + claude --resume after copying."""
    s = _session()
    result, _ = _invoke(["my-session", "--to", "personal"], [s])
    assert "textaccounts show personal" in result.output
    assert s.id in result.output


def test_migrate_dry_run_skips_copy():
    """--dry-run prints what would happen but does not call shutil.copy2."""
    s = _session()
    result, copy_mock = _invoke(["my-session", "--to", "personal", "--dry-run"], [s])
    assert result.exit_code == 0
    assert not copy_mock.called
    assert "dry-run" in result.output


def test_migrate_no_session_match():
    """migrate exits non-zero when no session matches the given name."""
    result, _ = _invoke(["nonexistent", "--to", "personal"], [])
    assert result.exit_code != 0


def test_migrate_no_jsonl_found():
    """migrate exits non-zero when the .jsonl cannot be located."""
    s = _session()
    result, _ = _invoke(["my-session", "--to", "personal"], [s], src_exists=False)
    assert result.exit_code != 0
    assert "Cannot locate" in result.output or result.exit_code != 0


def test_migrate_warns_when_dest_exists():
    """migrate notes that the destination already exists before overwriting."""
    s = _session()

    with patch("textsessions.cli.load", return_value=_cfg()), \
         patch("textsessions.cli.load_sessions", return_value=[s]), \
         patch("textsessions.profiles.validate_explicit_profile"), \
         patch("textsessions.profiles.env_for_profile", return_value={"CLAUDE_CONFIG_DIR": "/home/user/.claude-personal"}), \
         patch("textsessions.indexer.load_index", return_value={s.id: {"jsonl_path": f"/src/{s.id}.jsonl"}}), \
         patch("textsessions.config.detect_claude_dirs", return_value=[]), \
         patch("textsessions.indexer.reindex_repos", return_value=1), \
         patch("pathlib.Path.exists", return_value=True), \
         patch("pathlib.Path.mkdir"), \
         patch("textsessions.cli.shutil.copy2"):
        result = CliRunner().invoke(main, ["migrate", "my-session", "--to", "personal"])
    assert result.exit_code == 0
    assert "already has this session" in result.output
