"""Tests for resume command construction and cwd behaviour."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch


def test_resume_cmd_default_template():
    from textsessions.profiles import resume_cmd
    env = {"HOME": str(Path.home())}
    cmd = resume_cmd("abc123", "my-session", "work", env, claude_cmd_tpl="claude")
    assert cmd[0] == "fish"
    assert "claude --resume" in cmd[-1]
    assert "abc123" in cmd[-1]


def test_resume_cmd_profile_template_substituted():
    from textsessions.profiles import resume_cmd
    env = {"HOME": str(Path.home())}
    cmd = resume_cmd("abc123", "my-session", "work", env, claude_cmd_tpl="claude-{profile}")
    assert cmd[0] == "fish"
    assert "claude-work --resume" in cmd[-1]


def test_resume_cmd_cloak_overrides_template():
    """When CLAUDE_CONFIG_DIR is set (cloak active), always use plain claude."""
    from textsessions.profiles import resume_cmd
    env = {"HOME": str(Path.home()), "CLAUDE_CONFIG_DIR": "/some/cloak/dir"}
    cmd = resume_cmd("abc123", "my-session", "work", env, claude_cmd_tpl="claude-{profile}")
    assert "claude --resume" in cmd[-1]
    assert "claude-work" not in cmd[-1]


def test_resume_cmd_tmux_renames_window():
    from textsessions.profiles import resume_cmd
    env = {"HOME": str(Path.home())}
    with patch.dict(os.environ, {"TMUX": "/tmp/tmux-123/default,1234,0"}):
        cmd = resume_cmd("abc123", "my-session", "default", env)
    fish_script = cmd[-1]
    assert "tmux rename-window" in fish_script
    assert "my-session" in fish_script


def test_resume_cmd_tmux_prefixes_window_with_profile_initial():
    """Window name is prefixed with the profile's first letter: w-pathfinder."""
    from textsessions.profiles import resume_cmd
    env = {"HOME": str(Path.home())}
    with patch.dict(os.environ, {"TMUX": "/tmp/tmux-123/default,1234,0"}):
        cmd = resume_cmd("abc123", "pathfinder", "work", env)
    fish_script = cmd[-1]
    assert "w-pathfinder" in fish_script
    assert "CLAUDE_RESUME_NAME w-pathfinder" in fish_script


def test_resume_cmd_tmux_prefix_uses_personal_initial():
    from textsessions.profiles import resume_cmd
    env = {"HOME": str(Path.home())}
    with patch.dict(os.environ, {"TMUX": "/tmp/tmux-123/default,1234,0"}):
        cmd = resume_cmd("abc123", "refactor", "personal", env)
    assert "p-refactor" in cmd[-1]


def test_resume_cmd_tmux_prefix_fallback_to_session_id():
    """When no session name, prefix still applies to the id-stub fallback."""
    from textsessions.profiles import resume_cmd
    env = {"HOME": str(Path.home())}
    with patch.dict(os.environ, {"TMUX": "/tmp/tmux-123/default,1234,0"}):
        cmd = resume_cmd("abc123de", "", "work", env)
    assert "w-abc123de" in cmd[-1]


def test_resume_cmd_tmux_prefix_empty_profile():
    """Empty profile → no prefix, bare name used."""
    from textsessions.profiles import resume_cmd
    env = {"HOME": str(Path.home())}
    with patch.dict(os.environ, {"TMUX": "/tmp/tmux-123/default,1234,0"}):
        cmd = resume_cmd("abc123", "myname", "", env)
    fish_script = cmd[-1]
    assert "tmux rename-window myname" in fish_script
    assert "-myname" not in fish_script  # no dangling hyphen prefix


def test_resume_cmd_no_tmux_skips_rename():
    from textsessions.profiles import resume_cmd
    env = {"HOME": str(Path.home())}
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("TMUX", None)
        cmd = resume_cmd("abc123", "my-session", "default", env)
    assert "tmux rename-window" not in cmd[-1]
