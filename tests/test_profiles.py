"""Tests for profile detection helpers and build_launch_env."""

from __future__ import annotations

import os
import socket
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from textsessions.profiles import (
    aiproxy_available,
    aiproxy_running,
    build_launch_env,
    cloak_available,
    cloak_profile_dir,
    list_cloak_profiles,
)


# ---------------------------------------------------------------------------
# cloak_available
# ---------------------------------------------------------------------------


def test_cloak_available_false():
    """cloak_available returns False when cloak is not on PATH."""
    with patch("textsessions.profiles.shutil.which", return_value=None):
        assert cloak_available() is False


def test_cloak_available_true(tmp_path: Path):
    """cloak_available returns True when cloak binary is found on PATH."""
    fake_cloak = tmp_path / "cloak"
    fake_cloak.touch(mode=0o755)
    with patch("textsessions.profiles.shutil.which", return_value=str(fake_cloak)):
        assert cloak_available() is True


# ---------------------------------------------------------------------------
# list_cloak_profiles
# ---------------------------------------------------------------------------


def test_list_cloak_profiles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """list_cloak_profiles returns sorted profile names from ~/.cloak/profiles/."""
    profiles_dir = tmp_path / ".cloak" / "profiles"
    profiles_dir.mkdir(parents=True)
    (profiles_dir / "work").mkdir()
    (profiles_dir / "personal").mkdir()
    (profiles_dir / "default").mkdir()
    # A file (not dir) should be ignored
    (profiles_dir / "notadir.txt").write_text("x")

    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    result = list_cloak_profiles()
    assert result == ["default", "personal", "work"]


def test_list_cloak_profiles_no_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """list_cloak_profiles returns [] when ~/.cloak/profiles/ doesn't exist."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert list_cloak_profiles() == []


# ---------------------------------------------------------------------------
# aiproxy_running
# ---------------------------------------------------------------------------


def test_aiproxy_running_false():
    """aiproxy_running returns False when nothing is listening on 7474."""
    with patch("textsessions.profiles.socket.create_connection", side_effect=OSError):
        assert aiproxy_running() is False


def test_aiproxy_running_true():
    """aiproxy_running returns True when something is listening on 7474."""
    mock_conn = MagicMock()
    mock_conn.__enter__ = lambda s: s
    mock_conn.__exit__ = MagicMock(return_value=False)
    with patch("textsessions.profiles.socket.create_connection", return_value=mock_conn):
        assert aiproxy_running() is True


# ---------------------------------------------------------------------------
# build_launch_env
# ---------------------------------------------------------------------------


CLEAN_ENV = {"PATH": "/usr/bin:/bin"}


def test_build_launch_env_no_cloak(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """When cloak is not available, CLAUDE_CONFIG_DIR is not set."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    with (
        patch("textsessions.profiles.os.environ", CLEAN_ENV),
        patch("textsessions.profiles.shutil.which", return_value=None),
        patch("textsessions.profiles.aiproxy_running", return_value=False),
    ):
        env = build_launch_env("personal", {"cloak": True, "aiproxy": True})
    assert "CLAUDE_CONFIG_DIR" not in env


def test_build_launch_env_with_cloak(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """When cloak is available and profile dir exists, CLAUDE_CONFIG_DIR is set."""
    profile_dir = tmp_path / ".cloak" / "profiles" / "personal"
    profile_dir.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    with (
        patch("textsessions.profiles.os.environ", CLEAN_ENV),
        patch("textsessions.profiles.shutil.which", side_effect=lambda cmd: "/usr/bin/cloak" if cmd == "cloak" else None),
        patch("textsessions.profiles.aiproxy_running", return_value=False),
    ):
        env = build_launch_env("personal", {"cloak": True, "aiproxy": True})

    assert env["CLAUDE_CONFIG_DIR"] == str(profile_dir)


def test_build_launch_env_default_profile_no_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Default profile never sets CLAUDE_CONFIG_DIR."""
    profile_dir = tmp_path / ".cloak" / "profiles" / "default"
    profile_dir.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    with (
        patch("textsessions.profiles.os.environ", CLEAN_ENV),
        patch("textsessions.profiles.shutil.which", side_effect=lambda cmd: "/usr/bin/cloak" if cmd == "cloak" else None),
        patch("textsessions.profiles.aiproxy_running", return_value=False),
    ):
        env = build_launch_env("default", {"cloak": True, "aiproxy": True})

    assert "CLAUDE_CONFIG_DIR" not in env


def test_build_launch_env_cloak_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """When cloak integration is disabled in config, CLAUDE_CONFIG_DIR is not set."""
    profile_dir = tmp_path / ".cloak" / "profiles" / "personal"
    profile_dir.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    with (
        patch("textsessions.profiles.os.environ", CLEAN_ENV),
        patch("textsessions.profiles.shutil.which", side_effect=lambda cmd: "/usr/bin/cloak" if cmd == "cloak" else None),
        patch("textsessions.profiles.aiproxy_running", return_value=False),
    ):
        env = build_launch_env("personal", {"cloak": False, "aiproxy": False})

    assert "CLAUDE_CONFIG_DIR" not in env


def test_build_launch_env_with_aiproxy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """When ai-proxy is available and running, ANTHROPIC_BASE_URL is set."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    with (
        patch("textsessions.profiles.os.environ", CLEAN_ENV),
        patch("textsessions.profiles.shutil.which", side_effect=lambda cmd: "/usr/bin/ai-proxy" if cmd == "ai-proxy" else None),
        patch("textsessions.profiles.aiproxy_running", return_value=True),
    ):
        env = build_launch_env("default", {"cloak": True, "aiproxy": True})

    assert env["ANTHROPIC_BASE_URL"] == "http://localhost:7474"


def test_build_launch_env_aiproxy_not_running(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """When ai-proxy is installed but not running, ANTHROPIC_BASE_URL is not set."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    with (
        patch("textsessions.profiles.os.environ", CLEAN_ENV),
        patch("textsessions.profiles.shutil.which", side_effect=lambda cmd: "/usr/bin/ai-proxy" if cmd == "ai-proxy" else None),
        patch("textsessions.profiles.aiproxy_running", return_value=False),
    ):
        env = build_launch_env("default", {"cloak": True, "aiproxy": True})

    assert "ANTHROPIC_BASE_URL" not in env
