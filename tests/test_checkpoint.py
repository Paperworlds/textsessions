"""Tests for the textsessions-checkpoint spec implementation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from textsessions.checkpoint import (
    checkpoint_log_path,
    has_checkpoint_log,
    write_checkpoint_header,
    write_checkpoint_trailer,
    CHECKPOINT_SYSTEM_PROMPT,
)
from textsessions.sessions import Session


def _s(**kw) -> Session:
    base = dict(
        id="b2c3fcd9-7090-4216-b800-9ebf9782f03d",
        name="my-session",
        profile="work",
        last_active="2026-05-05 09:00",
        slug="my-session",
        repo_label="textsessions",
        repo_path=Path("/projects/textsessions"),
    )
    base.update(kw)
    return Session(**base)


# --- checkpoint_log_path / has_checkpoint_log --------------------------------

def test_checkpoint_log_path(tmp_path):
    sid = "abc123"
    p = checkpoint_log_path(sid, checkpoint_dir=tmp_path)
    assert p == tmp_path / "abc123.yaml"


def test_has_checkpoint_log_false(tmp_path):
    assert not has_checkpoint_log("nosuchid", checkpoint_dir=tmp_path)


def test_has_checkpoint_log_true(tmp_path):
    (tmp_path / "mysid.yaml").write_text("checkpoint_log: '0.1.0'\n")
    assert has_checkpoint_log("mysid", checkpoint_dir=tmp_path)


def test_session_has_checkpoint_log_property(tmp_path):
    s = _s(id="b2c3fcd9-7090-4216-b800-9ebf9782f03d")
    with patch("textsessions.checkpoint.CHECKPOINT_DIR", tmp_path):
        assert not s.has_checkpoint_log
        (tmp_path / f"{s.id}.yaml").write_text("checkpoint_log: '0.1.0'\n")
        assert s.has_checkpoint_log


# --- write_checkpoint_header -------------------------------------------------

def test_write_checkpoint_header_creates_file(tmp_path):
    s = _s()
    path = tmp_path / "header.yaml"
    write_checkpoint_header(path, s)
    assert path.exists()
    content = path.read_text()
    assert "checkpoint_log: '0.1.0'" in content
    assert s.id in content
    assert "started:" in content
    assert "repo: textsessions" in content
    assert "task: my-session" in content


def test_write_checkpoint_header_creates_parent_dir(tmp_path):
    s = _s()
    path = tmp_path / "deep" / "nested" / "session.yaml"
    write_checkpoint_header(path, s)
    assert path.exists()


def test_write_checkpoint_header_omits_empty_fields(tmp_path):
    s = _s(name="b2c3fcd9", repo_label="")  # name == short id, no repo_label
    path = tmp_path / "session.yaml"
    write_checkpoint_header(path, s)
    content = path.read_text()
    assert "repo:" not in content
    assert "task:" not in content


def test_write_checkpoint_header_includes_persona(tmp_path):
    from textsessions.sessions import Hint
    s = _s(hint=Hint(persona="agentic-pivot"))
    path = tmp_path / "session.yaml"
    write_checkpoint_header(path, s)
    assert "persona: agentic-pivot" in path.read_text()


# --- write_checkpoint_trailer ------------------------------------------------

def test_write_checkpoint_trailer_appends(tmp_path):
    path = tmp_path / "session.yaml"
    path.write_text("checkpoint_log: '0.1.0'\n")
    write_checkpoint_trailer(path, exit_code=0)
    content = path.read_text()
    assert "trailer: true" in content
    assert "ended:" in content
    assert "exit_code: 0" in content


def test_write_checkpoint_trailer_nonzero_exit(tmp_path):
    path = tmp_path / "session.yaml"
    path.write_text("checkpoint_log: '0.1.0'\n")
    write_checkpoint_trailer(path, exit_code=1)
    assert "exit_code: 1" in path.read_text()


def test_write_checkpoint_trailer_no_exit_code(tmp_path):
    path = tmp_path / "session.yaml"
    path.write_text("checkpoint_log: '0.1.0'\n")
    write_checkpoint_trailer(path)
    content = path.read_text()
    assert "trailer: true" in content
    assert "exit_code" not in content


def test_write_checkpoint_trailer_noop_if_missing(tmp_path):
    path = tmp_path / "nonexistent.yaml"
    write_checkpoint_trailer(path, exit_code=0)  # should not raise
    assert not path.exists()


# --- system prompt -----------------------------------------------------------

def test_checkpoint_system_prompt_mentions_env_var():
    assert "TS_CHECKPOINT_LOG" in CHECKPOINT_SYSTEM_PROMPT


def test_checkpoint_system_prompt_mentions_no_reread():
    assert "Never re-read" in CHECKPOINT_SYSTEM_PROMPT


# --- resume_cmd integration --------------------------------------------------

def test_resume_cmd_injects_append_system_prompt(tmp_path):
    from textsessions.profiles import resume_cmd
    s = _s()
    log_path = tmp_path / f"{s.id}.yaml"
    cmd = resume_cmd(s.id, s.name, "work", {}, checkpoint_log_path=log_path)
    full = " ".join(cmd)
    assert "--append-system-prompt" in full
    assert CHECKPOINT_SYSTEM_PROMPT in full


def test_resume_cmd_no_system_prompt_without_log():
    from textsessions.profiles import resume_cmd
    s = _s()
    cmd = resume_cmd(s.id, s.name, "work", {})
    assert "--append-system-prompt" not in " ".join(cmd)


# --- _resume_session integration (disabled path) ----------------------------

def test_resume_session_skips_checkpoint_when_disabled(tmp_path):
    """When config.checkpoint_log is False, no log file is created."""
    from click.testing import CliRunner
    from textsessions.cli import main
    from textsessions.config import Config, RepoConfig

    s = _s()
    cfg = Config(
        repos=[RepoConfig(path=Path("/projects/textsessions"), label="textsessions")],
        checkpoint_log=False,
    )
    run_mock = MagicMock(returncode=0)

    with (
        patch("textsessions.cli.load", return_value=cfg),
        patch("textsessions.cli.load_sessions", return_value=[s]),
        patch("textsessions.cli._resolve_repo_from_cwd", return_value=cfg.repos[0]),
        patch("textsessions.cli.subprocess.run", return_value=run_mock),
        patch.object(Path, "exists", return_value=True),
        patch("textsessions.checkpoint.CHECKPOINT_DIR", tmp_path),
    ):
        runner = CliRunner()
        runner.invoke(main, ["jump", "--dry-run"])
        assert not list(tmp_path.iterdir())
