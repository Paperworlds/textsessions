"""Tests for profile detection helpers and build_launch_env."""

from __future__ import annotations

import re
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


# ---------------------------------------------------------------------------
# Regression: cloak must not survive the migration
# These static-analysis tests catch any re-introduction of cloak symbols
# in source files that previously required manual cleanup after 004 ran.
# They do NOT touch the filesystem at runtime.
# ---------------------------------------------------------------------------

_SRC = Path(__file__).parent.parent / "src" / "textsessions"

# Symbols from the removed cloak integration that must never reappear.
_BANNED_CLOAK_SYMBOLS = re.compile(
    r"\b(cloak_available|cloak_profile_dir|list_cloak_profiles|cloak_version"
    r"|integrations\.cloak)\b"
)


def _source_files() -> list[Path]:
    return sorted(_SRC.rglob("*.py"))


def test_no_cloak_symbols_in_source():
    """No cloak function names or integrations.cloak attribute survive in source."""
    violations: list[str] = []
    for path in _source_files():
        text = path.read_text()
        for m in _BANNED_CLOAK_SYMBOLS.finditer(text):
            line_no = text[: m.start()].count("\n") + 1
            violations.append(f"{path.relative_to(_SRC.parent.parent)}:{line_no}: {m.group()!r}")
    assert not violations, "Cloak symbols found:\n" + "\n".join(violations)


def test_build_launch_env_callers_use_textaccounts_key():
    """Every build_launch_env call must pass 'textaccounts' key, not 'cloak'."""
    cloak_key = re.compile(r'build_launch_env\b.*?"cloak"', re.DOTALL)
    violations: list[str] = []
    for path in _source_files():
        text = path.read_text()
        # Simple line-by-line check: flag any line with both build_launch_env and "cloak"
        for i, line in enumerate(text.splitlines(), 1):
            if "build_launch_env" in line and '"cloak"' in line:
                violations.append(f"{path.relative_to(_SRC.parent.parent)}:{i}")
        # Also catch multi-line dict spread over adjacent lines
        if cloak_key.search(text):
            violations.append(f"{path.relative_to(_SRC.parent.parent)}: multi-line match")
    assert not violations, "'cloak' key passed to build_launch_env:\n" + "\n".join(violations)


def test_textaccounts_available_uses_module_constant(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """textaccounts_available() reads the overridable module constant, not a hardcoded path.

    This ensures tests can always monkeypatch _TEXTACCOUNTS_CONFIG to avoid
    touching real ~/.textaccounts/ and triggering TUI profile hints.
    """
    absent = tmp_path / "nowhere.yaml"
    monkeypatch.setattr(profiles_mod, "_TEXTACCOUNTS_CONFIG", absent)
    assert textaccounts_available() is False

    present = tmp_path / "here.yaml"
    present.write_text("version: 1\nprofiles: {}\n")
    monkeypatch.setattr(profiles_mod, "_TEXTACCOUNTS_CONFIG", present)
    assert textaccounts_available() is True
