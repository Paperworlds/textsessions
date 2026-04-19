"""Tests for `textsessions repos` CLI command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from textsessions.cli import main
from textsessions.config import Config, RepoConfig


def _cfg(repos: list[RepoConfig]) -> Config:
    return Config(repos=repos)


def test_repos_emits_repo_lines(tmp_path):
    """repos emits one REPO line per configured repo."""
    cfg = _cfg([
        RepoConfig(path=Path("/projects/foo"), label="foo", profile="work"),
        RepoConfig(path=Path("/projects/bar"), label="bar", profile="personal"),
    ])
    with patch("textsessions.cli.load", return_value=cfg):
        result = CliRunner().invoke(main, ["repos"])
    assert result.exit_code == 0
    lines = result.output.strip().splitlines()
    assert lines[0] == "REPO foo /projects/foo profile=work"
    assert lines[1] == "REPO bar /projects/bar profile=personal"


def test_repos_empty_config(tmp_path):
    """repos prints nothing and exits 0 when no repos configured (R06)."""
    cfg = _cfg([])
    with patch("textsessions.cli.load", return_value=cfg):
        result = CliRunner().invoke(main, ["repos"])
    assert result.exit_code == 0
    assert result.output.strip() == ""


def test_repos_nonexistent_path_still_emits(tmp_path):
    """repos emits REPO line even when path does not exist on disk (R07)."""
    cfg = _cfg([
        RepoConfig(path=Path("/does/not/exist"), label="ghost", profile="work"),
    ])
    with patch("textsessions.cli.load", return_value=cfg):
        result = CliRunner().invoke(main, ["repos"])
    assert result.exit_code == 0
    assert "REPO ghost /does/not/exist" in result.output


def test_repos_no_profile_omits_profile_key(tmp_path):
    """repos omits profile= key when profile is empty string."""
    cfg = _cfg([
        RepoConfig(path=Path("/projects/foo"), label="foo", profile=""),
    ])
    with patch("textsessions.cli.load", return_value=cfg):
        result = CliRunner().invoke(main, ["repos"])
    assert result.exit_code == 0
    assert result.output.strip() == "REPO foo /projects/foo"
