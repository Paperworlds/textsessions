"""Tests for _resolve_repo_from_cwd helper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from textsessions.cli import _resolve_repo_from_cwd
from textsessions.config import Config, RepoConfig


def _cfg(repos: list[RepoConfig]) -> Config:
    return Config(repos=repos)


def test_exact_match(tmp_path):
    """Returns repo when cwd == repo.path."""
    repo = RepoConfig(path=tmp_path, label="myrepo", profile="")
    cfg = _cfg([repo])
    with patch("textsessions.cli.Path.cwd", return_value=tmp_path):
        result = _resolve_repo_from_cwd(cfg)
    assert result is repo


def test_child_directory_match(tmp_path):
    """Returns repo when cwd is a subdirectory of repo.path."""
    child = tmp_path / "src" / "mypackage"
    child.mkdir(parents=True)
    repo = RepoConfig(path=tmp_path, label="myrepo", profile="")
    cfg = _cfg([repo])
    with patch("textsessions.cli.Path.cwd", return_value=child):
        result = _resolve_repo_from_cwd(cfg)
    assert result is repo


def test_deepest_match_wins(tmp_path):
    """Returns the most-specific (deepest) matching repo."""
    parent_repo = RepoConfig(path=tmp_path, label="parent", profile="")
    child_dir = tmp_path / "sub"
    child_dir.mkdir()
    child_repo = RepoConfig(path=child_dir, label="child", profile="")
    cfg = _cfg([parent_repo, child_repo])
    with patch("textsessions.cli.Path.cwd", return_value=child_dir):
        result = _resolve_repo_from_cwd(cfg)
    assert result is child_repo


def test_no_match_exits(tmp_path):
    """Exits with SystemExit when cwd does not match any repo."""
    other = tmp_path / "other"
    other.mkdir()
    repo = RepoConfig(path=tmp_path / "project", label="proj", profile="")
    cfg = _cfg([repo])
    with patch("textsessions.cli.Path.cwd", return_value=other):
        with pytest.raises(SystemExit):
            _resolve_repo_from_cwd(cfg)


def test_no_match_emits_error_message(tmp_path, capsys):
    """Error message includes the unmatched cwd."""
    other = tmp_path / "nowhere"
    other.mkdir()
    cfg = _cfg([RepoConfig(path=tmp_path / "project", label="proj", profile="")])
    with patch("textsessions.cli.Path.cwd", return_value=other):
        with pytest.raises(SystemExit):
            _resolve_repo_from_cwd(cfg)
    # click writes to stderr; capsys captures it
    err = capsys.readouterr().err
    assert str(other) in err


def test_custom_add_hint(tmp_path, capsys):
    """Custom add_hint appears in the error output."""
    other = tmp_path / "nowhere"
    other.mkdir()
    cfg = _cfg([RepoConfig(path=tmp_path / "project", label="proj", profile="")])
    with patch("textsessions.cli.Path.cwd", return_value=other):
        with pytest.raises(SystemExit):
            _resolve_repo_from_cwd(cfg, add_hint="Add it with: textsessions add .")
    err = capsys.readouterr().err
    assert "Add it with: textsessions add ." in err
