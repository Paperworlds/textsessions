"""Tests for `textsessions repo rename` CLI command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from textsessions.cli import main
from textsessions.config import Config, RepoConfig


def _cfg(repos: list[RepoConfig]) -> Config:
    return Config(repos=repos)


def test_repo_rename_updates_label(tmp_path):
    cfg = _cfg([
        RepoConfig(path=Path("/projects/foo"), label="foo", profile="work"),
    ])
    saved: dict = {}

    def _save(c: Config) -> None:
        saved["cfg"] = c

    with patch("textsessions.cli.load", return_value=cfg), \
         patch("textsessions.cli.save", side_effect=_save):
        result = CliRunner().invoke(main, ["repo", "rename", "foo", "bar"])
    assert result.exit_code == 0, result.output
    assert "foo" in result.output and "bar" in result.output
    assert saved["cfg"].repos[0].label == "bar"
    assert saved["cfg"].repos[0].path == Path("/projects/foo")  # path unchanged


def test_repo_rename_unknown_label(tmp_path):
    cfg = _cfg([RepoConfig(path=Path("/projects/foo"), label="foo", profile="work")])
    with patch("textsessions.cli.load", return_value=cfg):
        result = CliRunner().invoke(main, ["repo", "rename", "missing", "bar"])
    assert result.exit_code != 0
    assert "No repo with label 'missing'" in result.output


def test_repo_rename_collision(tmp_path):
    cfg = _cfg([
        RepoConfig(path=Path("/projects/foo"), label="foo", profile="work"),
        RepoConfig(path=Path("/projects/bar"), label="bar", profile="work"),
    ])
    with patch("textsessions.cli.load", return_value=cfg):
        result = CliRunner().invoke(main, ["repo", "rename", "foo", "bar"])
    assert result.exit_code != 0
    assert "already exists" in result.output


def test_repo_rename_noop(tmp_path):
    cfg = _cfg([RepoConfig(path=Path("/projects/foo"), label="foo", profile="work")])
    with patch("textsessions.cli.load", return_value=cfg), \
         patch("textsessions.cli.save") as save_mock:
        result = CliRunner().invoke(main, ["repo", "rename", "foo", "foo"])
    assert result.exit_code == 0
    assert "unchanged" in result.output.lower()
    save_mock.assert_not_called()
