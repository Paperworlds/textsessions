"""Tests for profile detection helpers and build_launch_env."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

import textsessions.profiles as profiles_mod
from textsessions.profiles import (
    aiproxy_available,
    aiproxy_running,
    build_launch_env,
    list_textaccounts_profiles,
    textaccounts_available,
    textaccounts_profile_dir,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_registry(config_path: Path, data: dict) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w") as f:
        yaml.safe_dump(data, f)


# ---------------------------------------------------------------------------
# textaccounts_available
# ---------------------------------------------------------------------------


def test_textaccounts_available_true(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """textaccounts_available returns True when profiles.yaml exists."""
    config_path = tmp_path / ".textaccounts" / "profiles.yaml"
    _write_registry(config_path, {"version": 1, "profiles": {}})
    monkeypatch.setattr(profiles_mod, "_TEXTACCOUNTS_CONFIG", config_path)
    assert textaccounts_available() is True


def test_textaccounts_available_false(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """textaccounts_available returns False when profiles.yaml is missing."""
    config_path = tmp_path / ".textaccounts" / "profiles.yaml"
    monkeypatch.setattr(profiles_mod, "_TEXTACCOUNTS_CONFIG", config_path)
    assert textaccounts_available() is False


# ---------------------------------------------------------------------------
# textaccounts_profile_dir
# ---------------------------------------------------------------------------


def test_textaccounts_profile_dir_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """textaccounts_profile_dir returns the path for a registered profile."""
    profile_path = tmp_path / "profiles" / "work"
    config_path = tmp_path / ".textaccounts" / "profiles.yaml"
    _write_registry(config_path, {
        "version": 1,
        "profiles": {
            "work": {"path": str(profile_path)},
        },
    })
    monkeypatch.setattr(profiles_mod, "_TEXTACCOUNTS_CONFIG", config_path)
    assert textaccounts_profile_dir("work") == profile_path


def test_textaccounts_profile_dir_unknown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """textaccounts_profile_dir returns None for an unregistered profile."""
    config_path = tmp_path / ".textaccounts" / "profiles.yaml"
    _write_registry(config_path, {"version": 1, "profiles": {"work": {"path": "/some/path"}}})
    monkeypatch.setattr(profiles_mod, "_TEXTACCOUNTS_CONFIG", config_path)
    assert textaccounts_profile_dir("personal") is None


def test_textaccounts_profile_dir_no_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """textaccounts_profile_dir returns None when profiles.yaml is missing."""
    config_path = tmp_path / ".textaccounts" / "profiles.yaml"
    monkeypatch.setattr(profiles_mod, "_TEXTACCOUNTS_CONFIG", config_path)
    assert textaccounts_profile_dir("work") is None


# ---------------------------------------------------------------------------
# list_textaccounts_profiles
# ---------------------------------------------------------------------------


def test_list_textaccounts_profiles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """list_textaccounts_profiles returns sorted profile names."""
    config_path = tmp_path / ".textaccounts" / "profiles.yaml"
    _write_registry(config_path, {
        "version": 1,
        "profiles": {
            "work": {"path": "/a"},
            "personal": {"path": "/b"},
            "default": {"path": "/c"},
        },
    })
    monkeypatch.setattr(profiles_mod, "_TEXTACCOUNTS_CONFIG", config_path)
    assert list_textaccounts_profiles() == ["default", "personal", "work"]


def test_list_textaccounts_profiles_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """list_textaccounts_profiles returns [] when file missing."""
    config_path = tmp_path / ".textaccounts" / "profiles.yaml"
    monkeypatch.setattr(profiles_mod, "_TEXTACCOUNTS_CONFIG", config_path)
    assert list_textaccounts_profiles() == []


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


def test_build_launch_env_sets_claude_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """build_launch_env sets CLAUDE_CONFIG_DIR when textaccounts profile is found."""
    profile_path = tmp_path / "profiles" / "work"
    config_path = tmp_path / ".textaccounts" / "profiles.yaml"
    _write_registry(config_path, {"version": 1, "profiles": {"work": {"path": str(profile_path)}}})
    monkeypatch.setattr(profiles_mod, "_TEXTACCOUNTS_CONFIG", config_path)

    with (
        patch("textsessions.profiles.os.environ", CLEAN_ENV),
        patch("textsessions.profiles.aiproxy_running", return_value=False),
    ):
        env = build_launch_env("work", {"textaccounts": True, "aiproxy": False})

    assert env["CLAUDE_CONFIG_DIR"] == str(profile_path)


def test_build_launch_env_no_config_dir_when_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """build_launch_env does not set CLAUDE_CONFIG_DIR when textaccounts unavailable."""
    config_path = tmp_path / ".textaccounts" / "profiles.yaml"
    monkeypatch.setattr(profiles_mod, "_TEXTACCOUNTS_CONFIG", config_path)

    with (
        patch("textsessions.profiles.os.environ", CLEAN_ENV),
        patch("textsessions.profiles.aiproxy_running", return_value=False),
    ):
        env = build_launch_env("work", {"textaccounts": True, "aiproxy": False})

    assert "CLAUDE_CONFIG_DIR" not in env


def test_build_launch_env_no_config_dir_for_unknown_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """build_launch_env does not set CLAUDE_CONFIG_DIR when profile not registered."""
    config_path = tmp_path / ".textaccounts" / "profiles.yaml"
    _write_registry(config_path, {"version": 1, "profiles": {"work": {"path": "/some/path"}}})
    monkeypatch.setattr(profiles_mod, "_TEXTACCOUNTS_CONFIG", config_path)

    with (
        patch("textsessions.profiles.os.environ", CLEAN_ENV),
        patch("textsessions.profiles.aiproxy_running", return_value=False),
    ):
        env = build_launch_env("personal", {"textaccounts": True, "aiproxy": False})

    assert "CLAUDE_CONFIG_DIR" not in env


def test_build_launch_env_with_aiproxy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """When ai-proxy is available and running, ANTHROPIC_BASE_URL is set."""
    config_path = tmp_path / ".textaccounts" / "profiles.yaml"
    monkeypatch.setattr(profiles_mod, "_TEXTACCOUNTS_CONFIG", config_path)

    with (
        patch("textsessions.profiles.os.environ", CLEAN_ENV),
        patch("textsessions.profiles.shutil.which", side_effect=lambda cmd: "/usr/bin/ai-proxy" if cmd == "ai-proxy" else None),
        patch("textsessions.profiles.aiproxy_running", return_value=True),
    ):
        env = build_launch_env("default", {"textaccounts": False, "aiproxy": True})

    assert env["ANTHROPIC_BASE_URL"] == "http://localhost:7474"


def test_build_launch_env_aiproxy_not_running(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """When ai-proxy is installed but not running, ANTHROPIC_BASE_URL is not set."""
    config_path = tmp_path / ".textaccounts" / "profiles.yaml"
    monkeypatch.setattr(profiles_mod, "_TEXTACCOUNTS_CONFIG", config_path)

    with (
        patch("textsessions.profiles.os.environ", CLEAN_ENV),
        patch("textsessions.profiles.shutil.which", side_effect=lambda cmd: "/usr/bin/ai-proxy" if cmd == "ai-proxy" else None),
        patch("textsessions.profiles.aiproxy_running", return_value=False),
    ):
        env = build_launch_env("default", {"textaccounts": False, "aiproxy": True})

    assert "ANTHROPIC_BASE_URL" not in env
