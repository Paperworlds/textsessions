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
    assert "my-sessi" in fish_script  # truncated to 8 chars


def test_resume_cmd_tmux_suffixes_window_with_profile_initial():
    """Window name is truncated to 8 chars and suffixed with the profile initial: pathfind-w."""
    from textsessions.profiles import resume_cmd
    env = {"HOME": str(Path.home())}
    with patch.dict(os.environ, {"TMUX": "/tmp/tmux-123/default,1234,0"}):
        cmd = resume_cmd("abc123", "pathfinder", "work", env)
    fish_script = cmd[-1]
    assert "pathfind-w" in fish_script
    assert "CLAUDE_RESUME_NAME pathfind-w" in fish_script


def test_resume_cmd_tmux_suffix_uses_personal_initial():
    from textsessions.profiles import resume_cmd
    env = {"HOME": str(Path.home())}
    with patch.dict(os.environ, {"TMUX": "/tmp/tmux-123/default,1234,0"}):
        cmd = resume_cmd("abc123", "refactor", "personal", env)
    assert "refactor-p" in cmd[-1]


def test_resume_cmd_tmux_suffix_fallback_to_session_id():
    """When no session name, suffix still applies to the id-stub fallback."""
    from textsessions.profiles import resume_cmd
    env = {"HOME": str(Path.home())}
    with patch.dict(os.environ, {"TMUX": "/tmp/tmux-123/default,1234,0"}):
        cmd = resume_cmd("abc123de", "", "work", env)
    assert "abc123de-w" in cmd[-1]


def test_resume_cmd_tmux_suffix_empty_profile():
    """Empty profile → no suffix, bare name used."""
    from textsessions.profiles import resume_cmd
    env = {"HOME": str(Path.home())}
    with patch.dict(os.environ, {"TMUX": "/tmp/tmux-123/default,1234,0"}):
        cmd = resume_cmd("abc123", "myname", "", env)
    fish_script = cmd[-1]
    assert "tmux rename-window myname" in fish_script
    assert "myname-" not in fish_script  # no dangling hyphen suffix


def test_resume_cmd_no_tmux_skips_rename():
    from textsessions.profiles import resume_cmd
    env = {"HOME": str(Path.home())}
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("TMUX", None)
        cmd = resume_cmd("abc123", "my-session", "default", env)
    assert "tmux rename-window" not in cmd[-1]
