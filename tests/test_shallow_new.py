"""Tests for `textsessions shallow new` CLI command."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from textsessions.cli import main


def _invoke(args, **patches):
    """Invoke `ts shallow new` with sensible defaults patched in.

    Default patches: textaccounts is installed, configured, has 'personal' as a
    profile, and the textaccounts binary is on PATH. Override by passing kwargs.
    """
    defaults = {
        "_HAS_TEXTACCOUNTS": True,
        "textaccounts_available_ret": True,
        "list_profiles_ret": ["personal", "work"],
        "which_ret": "/usr/local/bin/textaccounts",
        "subprocess_ret": MagicMock(returncode=0),
    }
    defaults.update(patches)

    with patch("textsessions.profiles._HAS_TEXTACCOUNTS", defaults["_HAS_TEXTACCOUNTS"]), \
         patch("textsessions.profiles.textaccounts_available", return_value=defaults["textaccounts_available_ret"]), \
         patch("textsessions.profiles.list_textaccounts_profiles", return_value=defaults["list_profiles_ret"]), \
         patch("textsessions.cli.shutil.which", return_value=defaults["which_ret"]), \
         patch("textsessions.cli.subprocess.run", return_value=defaults["subprocess_ret"]) as run_mock:
        result = CliRunner().invoke(main, ["shallow", "new", *args])
        return result, run_mock


# --- happy path ---------------------------------------------------------------

def test_shallow_new_minimal():
    """ts shallow new NAME --from PARENT shells out cleanly."""
    result, run_mock = _invoke(["scratch-1", "--from", "personal"])
    assert result.exit_code == 0
    run_mock.assert_called_once()
    cmd = run_mock.call_args[0][0]
    assert cmd == ["textaccounts", "create", "scratch-1", "--shallow", "--from", "personal"]


def test_shallow_new_with_owner():
    """--owner is forwarded; --ephemeral suppressed (owner implies it)."""
    result, run_mock = _invoke(["scratch-1", "--from", "personal", "--owner", "pp:run-7", "--ephemeral"])
    assert result.exit_code == 0
    cmd = run_mock.call_args[0][0]
    assert "--owner" in cmd and "pp:run-7" in cmd
    assert "--ephemeral" not in cmd  # owner implies it; don't double up


def test_shallow_new_explicit_ephemeral_no_owner():
    """--ephemeral alone (no --owner) is forwarded."""
    result, run_mock = _invoke(["scratch-1", "--from", "personal", "--ephemeral"])
    assert result.exit_code == 0
    cmd = run_mock.call_args[0][0]
    assert "--ephemeral" in cmd
    assert "--owner" not in cmd


def test_shallow_new_propagates_exit_code():
    """Non-zero exit from textaccounts surfaces via sys.exit."""
    result, _ = _invoke(["scratch-1", "--from", "personal"], subprocess_ret=MagicMock(returncode=2))
    assert result.exit_code == 2


# --- guard rails --------------------------------------------------------------

def test_shallow_new_textaccounts_not_installed():
    result, run_mock = _invoke(["scratch-1", "--from", "personal"], _HAS_TEXTACCOUNTS=False)
    assert result.exit_code != 0
    assert "textaccounts is not installed" in result.output
    run_mock.assert_not_called()


def test_shallow_new_textaccounts_not_configured():
    result, run_mock = _invoke(["scratch-1", "--from", "personal"], textaccounts_available_ret=False)
    assert result.exit_code != 0
    assert "not configured" in result.output
    run_mock.assert_not_called()


def test_shallow_new_unknown_parent():
    result, run_mock = _invoke(["scratch-1", "--from", "ghost"])
    assert result.exit_code != 0
    assert "ghost" in result.output and "not found" in result.output
    run_mock.assert_not_called()


def test_shallow_new_name_collision():
    """Refuse to create a profile that already exists."""
    result, run_mock = _invoke(["personal", "--from", "work"])
    assert result.exit_code != 0
    assert "already exists" in result.output
    run_mock.assert_not_called()


def test_shallow_new_textaccounts_binary_missing():
    """API present but CLI binary not on PATH → fail loudly."""
    result, run_mock = _invoke(["scratch-1", "--from", "personal"], which_ret=None)
    assert result.exit_code != 0
    assert "not on PATH" in result.output
    run_mock.assert_not_called()


def test_shallow_new_requires_from():
    """--from is required; click should error."""
    with patch("textsessions.profiles._HAS_TEXTACCOUNTS", True):
        result = CliRunner().invoke(main, ["shallow", "new", "scratch-1"])
    assert result.exit_code != 0
    assert "--from" in result.output or "Missing option" in result.output
