"""Tests for profile detection helpers and build_launch_env.

textaccounts integration is tested by mocking textaccounts.api — textsessions
never reads ~/.textaccounts/ directly. The actual API behavior is tested in
the textaccounts repo.
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from textsessions.profiles import (
    build_launch_env,
    list_textaccounts_profiles,
    textaccounts_available,
    textproxy_available,
    textproxy_running,
    textproxy_url,
)


# ---------------------------------------------------------------------------
# textaccounts_available / list — delegates to textaccounts.api
# ---------------------------------------------------------------------------


def test_textaccounts_available_delegates_to_api():
    """When textaccounts is installed, available() delegates to textaccounts.api."""
    import textsessions.profiles as mod
    if mod._HAS_TEXTACCOUNTS:
        # Real import worked — the function IS textaccounts.api.available
        with patch("textaccounts.api.load_registry") as mock_load:
            from textaccounts.config import ProfileRegistry, Profile
            mock_load.return_value = ProfileRegistry(
                profiles={"work": Profile(name="work", path=Path("/tmp/w"))}
            )
            assert mod.textaccounts_available() is True
            mock_load.return_value = ProfileRegistry()
            assert mod.textaccounts_available() is False


def test_textaccounts_available_false_when_not_installed():
    """Fallback stub returns False when textaccounts is not installed."""
    import textsessions.profiles as mod
    if mod._HAS_TEXTACCOUNTS:
        pytest.skip("textaccounts is installed in test env")
    assert mod.textaccounts_available() is False


# ---------------------------------------------------------------------------
# textproxy_running
# ---------------------------------------------------------------------------


def test_textproxy_running_false():
    """textproxy_running returns False when nothing is listening on 7474."""
    with patch("textsessions.profiles.socket.create_connection", side_effect=OSError):
        assert textproxy_running() is False


def test_textproxy_running_true():
    """textproxy_running returns True when something is listening on 7474."""
    mock_conn = MagicMock()
    mock_conn.__enter__ = lambda s: s
    mock_conn.__exit__ = MagicMock(return_value=False)
    with patch("textsessions.profiles.socket.create_connection", return_value=mock_conn):
        assert textproxy_running() is True


# ---------------------------------------------------------------------------
# build_launch_env
# ---------------------------------------------------------------------------


CLEAN_ENV = {"PATH": "/usr/bin:/bin"}


def test_build_launch_env_sets_claude_config_dir():
    """build_launch_env sets CLAUDE_CONFIG_DIR when textaccounts returns env vars."""
    with (
        patch("textsessions.profiles._HAS_TEXTACCOUNTS", True),
        patch("textsessions.profiles.textaccounts_available", return_value=True),
        patch("textsessions.profiles._ta_env_for_profile", return_value={"CLAUDE_CONFIG_DIR": "/path/to/work"}),
        patch("textsessions.profiles.os.environ", CLEAN_ENV),
        patch("textsessions.profiles.textproxy_running", return_value=False),
    ):
        env = build_launch_env("work", {"textaccounts": True, "textproxy": False})

    assert env["CLAUDE_CONFIG_DIR"] == "/path/to/work"


def test_build_launch_env_no_config_dir_when_not_installed():
    """build_launch_env does not set CLAUDE_CONFIG_DIR when textaccounts not installed."""
    with (
        patch("textsessions.profiles._HAS_TEXTACCOUNTS", False),
        patch("textsessions.profiles.os.environ", CLEAN_ENV),
        patch("textsessions.profiles.textproxy_running", return_value=False),
    ):
        env = build_launch_env("work", {"textaccounts": True, "textproxy": False})

    assert "CLAUDE_CONFIG_DIR" not in env


def test_build_launch_env_no_config_dir_when_disabled():
    """build_launch_env does not set CLAUDE_CONFIG_DIR when textaccounts disabled in config."""
    with (
        patch("textsessions.profiles._HAS_TEXTACCOUNTS", True),
        patch("textsessions.profiles.os.environ", CLEAN_ENV),
        patch("textsessions.profiles.textproxy_running", return_value=False),
    ):
        env = build_launch_env("work", {"textaccounts": False, "textproxy": False})

    assert "CLAUDE_CONFIG_DIR" not in env


def test_build_launch_env_unknown_profile_no_crash():
    """build_launch_env handles unknown profile gracefully (ValueError from textaccounts)."""
    with (
        patch("textsessions.profiles._HAS_TEXTACCOUNTS", True),
        patch("textsessions.profiles.textaccounts_available", return_value=True),
        patch("textsessions.profiles._ta_env_for_profile", side_effect=ValueError("not found")),
        patch("textsessions.profiles.os.environ", CLEAN_ENV),
        patch("textsessions.profiles.textproxy_running", return_value=False),
    ):
        env = build_launch_env("nope", {"textaccounts": True, "textproxy": False})

    assert "CLAUDE_CONFIG_DIR" not in env


def test_build_launch_env_default_profile_no_config_dir():
    """build_launch_env with 'default' profile gets empty env from textaccounts."""
    with (
        patch("textsessions.profiles._HAS_TEXTACCOUNTS", True),
        patch("textsessions.profiles.textaccounts_available", return_value=True),
        patch("textsessions.profiles._ta_env_for_profile", return_value={}),
        patch("textsessions.profiles.os.environ", CLEAN_ENV),
        patch("textsessions.profiles.textproxy_running", return_value=False),
    ):
        env = build_launch_env("default", {"textaccounts": True, "textproxy": False})

    assert "CLAUDE_CONFIG_DIR" not in env


def test_build_launch_env_with_textproxy():
    """When textproxy is available and running, ANTHROPIC_BASE_URL is set."""
    with (
        patch("textsessions.profiles._HAS_TEXTACCOUNTS", False),
        patch("textsessions.profiles.os.environ", CLEAN_ENV),
        patch("textsessions.profiles.shutil.which", side_effect=lambda cmd: "/usr/bin/textproxy" if cmd == "textproxy" else None),
        patch("textsessions.profiles.textproxy_running", return_value=True),
    ):
        env = build_launch_env("default", {"textaccounts": False, "textproxy": True})

    assert env["ANTHROPIC_BASE_URL"] == textproxy_url("default")


def test_build_launch_env_textproxy_not_running():
    """When textproxy is not running, ANTHROPIC_BASE_URL is cleared from env."""
    stale_env = {**CLEAN_ENV, "ANTHROPIC_BASE_URL": "http://localhost:7474"}
    with (
        patch("textsessions.profiles._HAS_TEXTACCOUNTS", False),
        patch("textsessions.profiles.os.environ", stale_env),
        patch("textsessions.profiles.textproxy_running", return_value=False),
    ):
        env = build_launch_env("default", {"textaccounts": False, "textproxy": True})

    assert "ANTHROPIC_BASE_URL" not in env


def test_build_launch_env_textproxy_disabled_preserves_url():
    """When textproxy integration is disabled, ANTHROPIC_BASE_URL is left untouched."""
    stale_env = {**CLEAN_ENV, "ANTHROPIC_BASE_URL": "http://localhost:7474"}
    with (
        patch("textsessions.profiles._HAS_TEXTACCOUNTS", False),
        patch("textsessions.profiles.os.environ", stale_env),
        patch("textsessions.profiles.textproxy_running", return_value=False),
    ):
        env = build_launch_env("default", {"textaccounts": False, "textproxy": False})

    assert env["ANTHROPIC_BASE_URL"] == "http://localhost:7474"



# ---------------------------------------------------------------------------
# Regression: cloak must not survive the migration
# ---------------------------------------------------------------------------

_SRC = Path(__file__).parent.parent / "src" / "textsessions"

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
        for i, line in enumerate(text.splitlines(), 1):
            if "build_launch_env" in line and '"cloak"' in line:
                violations.append(f"{path.relative_to(_SRC.parent.parent)}:{i}")
        if cloak_key.search(text):
            violations.append(f"{path.relative_to(_SRC.parent.parent)}: multi-line match")
    assert not violations, "'cloak' key passed to build_launch_env:\n" + "\n".join(violations)
