"""Tests for _repo_for_cwd startup filter helper."""

from __future__ import annotations

from pathlib import Path

import pytest

from textsessions.config import Config, RepoConfig
from textsessions.tui.app import _repo_for_cwd


def _make_config(*paths: tuple[str, str]) -> Config:
    """Build a Config with repos from (path_str, label) pairs."""
    repos = [RepoConfig(path=Path(p), label=label) for p, label in paths]
    return Config(repos=repos)


def test_repo_for_cwd_match(tmp_path, monkeypatch):
    """cwd inside a configured repo returns that repo."""
    repo_path = tmp_path / "myrepo"
    cwd = repo_path / "src" / "pkg"
    cwd.mkdir(parents=True)
    monkeypatch.chdir(cwd)
    config = _make_config((str(repo_path), "myrepo"))
    result, is_parent = _repo_for_cwd(config)
    assert result is not None
    assert result.label == "myrepo"
    assert is_parent is False


def test_repo_for_cwd_no_match(tmp_path, monkeypatch):
    """cwd unrelated to any configured repo returns None."""
    repo_path = tmp_path / "myrepo"
    repo_path.mkdir()
    unrelated = tmp_path / "other"
    unrelated.mkdir()
    monkeypatch.chdir(unrelated)
    config = _make_config((str(repo_path), "myrepo"))
    result, is_parent = _repo_for_cwd(config)
    assert result is None
    assert is_parent is False


def test_repo_for_cwd_closest(tmp_path, monkeypatch):
    """cwd inside a nested repo returns the closest (longest path) match."""
    parent = tmp_path / "projects"
    child = tmp_path / "projects" / "sub"
    cwd = child / "src"
    cwd.mkdir(parents=True)
    monkeypatch.chdir(cwd)
    config = _make_config(
        (str(parent), "parent-label"),
        (str(child), "child-label"),
    )
    result, is_parent = _repo_for_cwd(config)
    assert result is not None
    assert result.label == "child-label"


def test_repo_for_cwd_parent_match_warns(tmp_path, monkeypatch):
    """cwd in an unconfigured git repo under a parent repo → is_parent_match=True."""
    parent = tmp_path / "projects"
    parent.mkdir()
    child = parent / "subrepo"
    child.mkdir()
    (child / ".git").mkdir()  # it's a git repo but not configured
    monkeypatch.chdir(child)
    config = _make_config((str(parent), "parent-label"))
    result, is_parent = _repo_for_cwd(config)
    assert result is not None
    assert result.label == "parent-label"
    assert is_parent is True
