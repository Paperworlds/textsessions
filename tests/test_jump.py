"""Tests for `textsessions jump` CLI command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from textsessions.cli import main
from textsessions.config import Config, RepoConfig
from textsessions.sessions import Hint, Session


def _cfg(repos: list[RepoConfig] | None = None) -> Config:
    return Config(repos=repos or [
        RepoConfig(path=Path("/projects/foo"), label="foo", profile="work"),
        RepoConfig(path=Path("/projects/bar"), label="bar", profile="personal"),
    ])


def _s(**kw) -> Session:
    base = dict(
        id="a" * 32,
        name="abc",
        profile="work",
        last_active="2026-05-03 12:00",
        slug="something",
        repo_label="foo",
        repo_path=Path("/projects/foo"),
    )
    base.update(kw)
    return Session(**base)


def _invoke(args, sessions, *, exists: bool = True, cfg: Config | None = None):
    """Run `ts jump` with patches: load() + load_sessions() + repo_path.exists().

    Returns (result, run_mock) like other test files.
    """
    cfg = cfg or _cfg()
    with patch("textsessions.cli.load", return_value=cfg), \
         patch("textsessions.cli.load_sessions", return_value=sessions), \
         patch("pathlib.Path.exists", return_value=exists), \
         patch("textsessions.cli.subprocess.run", return_value=MagicMock(returncode=0)) as run_mock, \
         patch("textsessions.profiles.build_launch_env", return_value={}), \
         patch("textsessions.profiles.resume_cmd", return_value=["fish", "-c", "claude"]):
        result = CliRunner().invoke(main, ["jump", *args])
    return result, run_mock


# --- happy path -------------------------------------------------------------

def test_jump_picks_latest_in_repo():
    """Default jump picks the most recent session by last_active."""
    older = _s(name="older", last_active="2026-05-01 10:00", id="o" * 32)
    newer = _s(name="newer", last_active="2026-05-03 14:00", id="n" * 32)
    # load_sessions returns newest-first per the real sort, mirror that.
    result, run = _invoke(["foo"], [newer, older])
    assert result.exit_code == 0
    assert "resuming newer" in (result.output + result.stderr)
    run.assert_called_once()


def test_jump_dry_run_does_not_exec():
    s = _s(name="latest")
    result, run = _invoke(["foo", "--dry-run"], [s])
    assert result.exit_code == 0
    assert "dry-run" in (result.output + result.stderr)
    run.assert_not_called()


# --- filtering --------------------------------------------------------------

def test_jump_skips_automated():
    """pp-worker / CI sessions are skipped; user wants their interactive row."""
    automated = _s(name="bot", tags=["worker"], last_active="2026-05-03 18:00", id="b" * 32)
    human = _s(name="human", last_active="2026-05-03 14:00", id="h" * 32)
    result, _ = _invoke(["foo"], [automated, human])
    assert "resuming human" in (result.output + result.stderr)
    assert "resuming bot" not in (result.output + result.stderr)


def test_jump_skips_orphans():
    """Hex-named throwaways are not what 'jump' means."""
    orphan = _s(name="abc12", last_active="2026-05-03 18:00", id="o" * 32)  # 5-char hex
    real = _s(name="real-work", last_active="2026-05-03 14:00", id="r" * 32)
    result, _ = _invoke(["foo"], [orphan, real])
    assert "resuming real-work" in (result.output + result.stderr)


def test_jump_matches_recursive_child_repos():
    """`personal` should also pick up sessions in `personal/textread`."""
    cfg = _cfg([RepoConfig(path=Path("/p/personal"), label="personal", profile="personal")])
    child = _s(name="child-sess", repo_label="personal/textread", repo_path=Path("/p/personal/textread"))
    result, _ = _invoke(["personal"], [child], cfg=cfg)
    assert result.exit_code == 0


# --- --lead -----------------------------------------------------------------

def test_jump_lead_matches_pinned():
    pinned = _s(name="pinned", pinned=True, last_active="2026-05-01 10:00", id="p" * 32)
    plain_newer = _s(name="newer", last_active="2026-05-03 14:00", id="n" * 32)
    # load_sessions sorts pinned-first, so pinned comes before plain_newer
    result, _ = _invoke(["foo", "--lead"], [pinned, plain_newer])
    assert "resuming pinned" in (result.output + result.stderr)


def test_jump_lead_matches_label():
    lead = _s(name="lead-sess", hint=Hint(labels=["lead"]), last_active="2026-05-02 10:00", id="l" * 32)
    plain = _s(name="plain", last_active="2026-05-03 14:00", id="p" * 32)
    result, _ = _invoke(["foo", "--lead"], [plain, lead])
    assert "resuming lead-sess" in (result.output + result.stderr)


def test_jump_lead_picks_most_recent_of_candidates():
    older_pinned = _s(name="old-pin", pinned=True, last_active="2026-05-01 10:00", id="1" * 32)
    newer_lead = _s(name="new-lead", hint=Hint(labels=["lead"]), last_active="2026-05-03 14:00", id="2" * 32)
    # In real sort order, both are pinned-first or sorted by last_active; we pass them already in order.
    result, _ = _invoke(["foo", "--lead"], [newer_lead, older_pinned])
    assert "resuming new-lead" in (result.output + result.stderr)


def test_jump_lead_no_candidate_errors():
    plain = _s(name="plain")
    result, run = _invoke(["foo", "--lead"], [plain])
    assert result.exit_code == 1
    assert "No pinned or 'lead'-labelled session" in (result.output + result.stderr)
    run.assert_not_called()


# --- error paths ------------------------------------------------------------

def test_jump_no_sessions_in_repo():
    result, run = _invoke(["foo"], [])
    assert result.exit_code == 1
    assert "No interactive sessions in 'foo'" in (result.output + result.stderr)
    run.assert_not_called()


def test_jump_unknown_repo():
    result, run = _invoke(["nonexistent"], [_s()])
    assert result.exit_code != 0
    assert "No repo with label 'nonexistent'" in (result.output + result.stderr)
    run.assert_not_called()


def test_jump_repo_path_disappeared():
    s = _s()
    result, run = _invoke(["foo"], [s], exists=False)
    assert result.exit_code == 1
    assert "no longer exists" in (result.output + result.stderr)
    run.assert_not_called()


def test_jump_no_repos_configured():
    cfg = Config(repos=[])
    result, run = _invoke(["foo"], [], cfg=cfg)
    assert result.exit_code == 1
    assert "No repos configured" in (result.output + result.stderr)
    run.assert_not_called()


# --- CWD fallback -----------------------------------------------------------

def test_jump_resolves_text_prefix_sugar():
    """`ts jump proxy` should resolve to repo labelled `textproxy`."""
    cfg = Config(repos=[
        RepoConfig(path=Path("/p/textproxy"), label="textproxy", profile="personal"),
    ])
    s = _s(name="proxy-sess", repo_label="textproxy", repo_path=Path("/p/textproxy"))
    result, _ = _invoke(["proxy"], [s], cfg=cfg)
    assert result.exit_code == 0
    assert "resuming proxy-sess" in (result.output + result.stderr)


def test_jump_exact_match_wins_over_sugar():
    """If a repo literally named 'proxy' exists, sugar shouldn't override it."""
    cfg = Config(repos=[
        RepoConfig(path=Path("/p/textproxy"), label="textproxy", profile="x"),
        RepoConfig(path=Path("/p/proxy"), label="proxy", profile="x"),
    ])
    a = _s(name="text-one", repo_label="textproxy", repo_path=Path("/p/textproxy"))
    b = _s(name="plain-one", repo_label="proxy", repo_path=Path("/p/proxy"))
    result, _ = _invoke(["proxy"], [a, b], cfg=cfg)
    assert "resuming plain-one" in (result.output + result.stderr)


def test_jump_no_arg_uses_cwd():
    """No positional repo → falls back to _resolve_repo_from_cwd."""
    cfg = _cfg()
    s = _s(name="from-cwd", repo_label="foo")
    repo_match = cfg.repos[0]  # foo
    with patch("textsessions.cli.load", return_value=cfg), \
         patch("textsessions.cli.load_sessions", return_value=[s]), \
         patch("textsessions.cli._resolve_repo_from_cwd", return_value=repo_match) as cwd_mock, \
         patch("pathlib.Path.exists", return_value=True), \
         patch("textsessions.cli.subprocess.run", return_value=MagicMock(returncode=0)), \
         patch("textsessions.profiles.build_launch_env", return_value={}), \
         patch("textsessions.profiles.resume_cmd", return_value=["fish", "-c", "claude"]):
        result = CliRunner().invoke(main, ["jump"])
    assert result.exit_code == 0
    cwd_mock.assert_called_once_with(cfg)
    assert "resuming from-cwd" in (result.output + result.stderr)
