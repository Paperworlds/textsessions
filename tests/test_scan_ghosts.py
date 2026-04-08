"""Integration tests for scan-ghosts CLI command."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from click.testing import CliRunner

from textsessions.cli import main
from textsessions.config import Config, ProxyConfig, RepoConfig


def make_yaml_index(sessions: list[dict]) -> dict:
    return {
        s["id"]: {
            "name": s.get("name", s["id"][:5]),
            "profile": s.get("profile", "personal"),
            "last_active": s.get("last_active", "2026-04-07 12:00"),
            "slug": s.get("slug", "hello"),
            "tags": s.get("tags", []),
            "priority": s.get("priority", ""),
        }
        for s in sessions
    }


@pytest.fixture
def fake_env(tmp_path):
    """Set up a fake STATE_DIR with two repos: one real, one ghost."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    real_repo = tmp_path / "real-repo"
    real_repo.mkdir()
    (real_repo / ".git").mkdir()

    ghost_repo = tmp_path / "ghost-repo"  # does NOT exist on disk

    # Real repo key
    real_key = str(real_repo).replace("/", "-")
    ghost_key = str(ghost_repo).replace("/", "-")

    real_sessions = [
        {"id": "a" * 32, "name": "aaaaa", "slug": "test test", "tags": [], "priority": ""},
        {"id": "b" * 32, "name": "real-work", "slug": "implement the oauth flow with refresh tokens and expiry handling properly", "tags": ["daily"], "priority": "1"},
    ]
    ghost_sessions = [
        {"id": "c" * 32, "name": "ccccc", "slug": "hello sir", "tags": [], "priority": ""},
    ]

    (state_dir / f"{real_key}.yaml").write_text(
        yaml.safe_dump(make_yaml_index(real_sessions))
    )
    (state_dir / f"{ghost_key}.yaml").write_text(
        yaml.safe_dump(make_yaml_index(ghost_sessions))
    )

    config = Config(
        repos=[
            RepoConfig(path=real_repo, label="real", profile="personal"),
            RepoConfig(path=ghost_repo, label="ghost", profile="personal"),
        ],
        proxy=ProxyConfig(cache_dir=tmp_path / "proxy"),
    )

    return config, state_dir, real_repo, ghost_repo, real_key, ghost_key


def test_scan_ghosts_json_dry_run(fake_env):
    config, state_dir, real_repo, ghost_repo, real_key, ghost_key = fake_env

    runner = CliRunner()
    with patch("textsessions.cli.load", return_value=config), \
         patch("textsessions.sessions.STATE_DIR", state_dir):
        result = runner.invoke(main, ["scan-ghosts", "--json"])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)

    ids = {d["id"] for d in data}
    kinds = {d["kind"] for d in data}

    # The ghost repo session should appear
    assert "c" * 32 in ids
    assert "ghost" in kinds

    # The orphan in real repo (short slug, no metadata)
    assert "a" * 32 in ids
    assert "orphan" in kinds

    # The tagged/prioritised session should NOT appear
    assert "b" * 32 not in ids


def test_scan_ghosts_dry_run_no_mutations(fake_env):
    """Default invocation (no flags) must not touch the index."""
    config, state_dir, real_repo, ghost_repo, real_key, ghost_key = fake_env
    before = (state_dir / f"{real_key}.yaml").read_text()

    runner = CliRunner()
    with patch("textsessions.cli.load", return_value=config), \
         patch("textsessions.sessions.STATE_DIR", state_dir):
        result = runner.invoke(main, ["scan-ghosts"])

    assert result.exit_code == 0, result.output
    assert "Dry run" in result.output
    assert (state_dir / f"{real_key}.yaml").read_text() == before


def test_scan_ghosts_archive(fake_env):
    """--archive should tag ghost/orphan sessions as 'archived', not delete them."""
    config, state_dir, real_repo, ghost_repo, real_key, ghost_key = fake_env

    runner = CliRunner()
    with patch("textsessions.cli.load", return_value=config), \
         patch("textsessions.sessions.STATE_DIR", state_dir), \
         patch("textsessions.indexer.STATE_DIR", state_dir), \
         patch("textsessions.indexer.LEGACY_INDEX_DIR", state_dir / "legacy"):
        result = runner.invoke(main, ["scan-ghosts", "--archive"])

    assert result.exit_code == 0, result.output
    assert "Archived" in result.output

    # Orphan (a*32) should still exist but have 'archived' tag
    real_index = yaml.safe_load((state_dir / f"{real_key}.yaml").read_text()) or {}
    assert "a" * 32 in real_index  # not deleted
    assert "archived" in real_index["a" * 32].get("tags", [])

    # The tagged/priority session should be untouched
    assert "b" * 32 in real_index
    assert "archived" not in real_index["b" * 32].get("tags", [])

    # Ghost repo session should still exist but be archived
    ghost_index = yaml.safe_load((state_dir / f"{ghost_key}.yaml").read_text()) or {}
    assert "c" * 32 in ghost_index
    assert "archived" in ghost_index["c" * 32].get("tags", [])


def test_scan_ghosts_delete(fake_env):
    config, state_dir, real_repo, ghost_repo, real_key, ghost_key = fake_env

    runner = CliRunner()
    with patch("textsessions.cli.load", return_value=config), \
         patch("textsessions.sessions.STATE_DIR", state_dir):
        result = runner.invoke(main, ["scan-ghosts", "--delete", "--yes"])

    assert result.exit_code == 0, result.output
    assert "Deleted" in result.output

    # Orphan (a*32) should be gone from real repo index
    real_index = yaml.safe_load((state_dir / f"{real_key}.yaml").read_text()) or {}
    assert "a" * 32 not in real_index
    assert "b" * 32 in real_index  # tagged session preserved

    # Ghost repo session should be gone
    ghost_index = yaml.safe_load((state_dir / f"{ghost_key}.yaml").read_text()) or {}
    assert "c" * 32 not in ghost_index


def test_scan_ghosts_delete_requires_yes(fake_env):
    """--delete without --yes should prompt, not auto-delete."""
    config, state_dir, real_repo, ghost_repo, real_key, ghost_key = fake_env
    before = (state_dir / f"{real_key}.yaml").read_text()

    runner = CliRunner()
    with patch("textsessions.cli.load", return_value=config), \
         patch("textsessions.sessions.STATE_DIR", state_dir):
        # Provide 'n' to the confirmation prompt
        result = runner.invoke(main, ["scan-ghosts", "--delete"], input="n\n")

    assert result.exit_code != 0 or "Deleted" not in result.output
    # Index should be unchanged
    assert (state_dir / f"{real_key}.yaml").read_text() == before
