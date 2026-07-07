"""Tests for `textsessions pin` / `unpin` CLI commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from textsessions.cli import main
from textsessions.config import Config, RepoConfig
from textsessions.sessions import Session


def _cfg() -> Config:
    return Config(repos=[RepoConfig(path=Path("/projects/foo"), label="foo", profile="work")])


def _s(**kw) -> Session:
    base = dict(
        id="abc12345" + "0" * 24,
        name="my-sess",
        profile="work",
        last_active="2026-05-03 12:00",
        slug="x",
        repo_label="foo",
        repo_path=Path("/projects/foo"),
    )
    base.update(kw)
    return Session(**base)


def _invoke(verb: str, name: str = "my-sess"):
    cfg = _cfg()
    s = _s()
    with patch("textsessions.cli.load", return_value=cfg), \
         patch("textsessions.cli._resolve_session_by_name", return_value=s), \
         patch("textsessions.indexer.mutate_index") as mutate:
        result = CliRunner().invoke(main, [verb, name])
    return result, mutate, s


def test_pin_sets_pinned_true():
    result, mutate, s = _invoke("pin")
    assert result.exit_code == 0
    assert "pinned" in result.output
    assert s.id[:8] in result.output

    # Verify mutate_index was called with a function that pins
    mutate.assert_called_once()
    fn = mutate.call_args[0][2]
    fake_index: dict = {s.id: {}}
    fn(fake_index, s.id)
    assert fake_index[s.id]["pinned"] is True


def test_unpin_clears_pinned():
    result, mutate, s = _invoke("unpin")
    assert result.exit_code == 0
    assert "unpinned" in result.output

    fn = mutate.call_args[0][2]
    fake_index: dict = {s.id: {"pinned": True}}
    fn(fake_index, s.id)
    assert "pinned" not in fake_index[s.id]


def test_pin_nonexistent_session_exits():
    """If _resolve_session_by_name can't find the session, command fails."""
    cfg = _cfg()

    def raise_no_match(name, config):
        import sys
        import click
        click.echo(f"No session matching '{name}'", err=True)
        sys.exit(1)

    with patch("textsessions.cli.load", return_value=cfg), \
         patch("textsessions.cli._resolve_session_by_name", side_effect=raise_no_match):
        result = CliRunner().invoke(main, ["pin", "ghost"])
    assert result.exit_code == 1
