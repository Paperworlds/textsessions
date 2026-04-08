"""Tests for resume command construction."""

from __future__ import annotations

import pytest


def _build_resume_cmd(profile: str, resume_id: str) -> list[str]:
    """Replicate the command-building logic from app.py."""
    cmd = ["claude", "--resume", resume_id]
    if profile != "default":
        cmd = ["claude", "--my-profile", profile, "--resume", resume_id]
    return cmd


@pytest.mark.parametrize("profile,resume_id,expected", [
    (
        "default",
        "abc123",
        ["claude", "--resume", "abc123"],
    ),
    (
        "personal",
        "def456",
        ["claude", "--my-profile", "personal", "--resume", "def456"],
    ),
    (
        "work",
        "ghi789",
        ["claude", "--my-profile", "work", "--resume", "ghi789"],
    ),
])
def test_resume_cmd(profile: str, resume_id: str, expected: list[str]) -> None:
    assert _build_resume_cmd(profile, resume_id) == expected


def test_resume_default_does_not_include_my_profile() -> None:
    cmd = _build_resume_cmd("default", "xyz")
    assert "--my-profile" not in cmd


def test_resume_non_default_includes_my_profile() -> None:
    cmd = _build_resume_cmd("personal", "xyz")
    assert "--my-profile" in cmd
    idx = cmd.index("--my-profile")
    assert cmd[idx + 1] == "personal"
