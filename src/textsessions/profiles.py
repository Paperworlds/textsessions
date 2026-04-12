"""Profile and integration detection helpers for textsessions.

Three tiers for profile resolution:
  1. textaccounts installed → delegates to textaccounts.api (auto-discovers profiles,
     sets CLAUDE_CONFIG_DIR). Zero config.
  2. No textaccounts, custom commands → user sets claude_cmd = "claude-{profile}" in
     config.toml. Each repo's profile name is substituted into the template.
  3. Single account → plain "claude", no profile switching.

Never auto-installs anything — only detects and guides.
"""

from __future__ import annotations

import os
import shutil
import socket

# --- textaccounts integration (optional dependency) --------------------------
# All textaccounts knowledge is delegated to its public API. textsessions never
# reads ~/.textaccounts/ directly — that's textaccounts' business.

try:
    from textaccounts.api import (
        available as textaccounts_available,
        env_for_profile as _ta_env_for_profile,
        list_profiles as list_textaccounts_profiles,
    )
    _HAS_TEXTACCOUNTS = True
except ImportError:
    _HAS_TEXTACCOUNTS = False

    def textaccounts_available() -> bool:  # type: ignore[misc]
        return False

    def list_textaccounts_profiles() -> list[str]:  # type: ignore[misc]
        return []

    def _ta_env_for_profile(name: str) -> dict[str, str]:
        return {}


# --- textproxy integration ---------------------------------------------------

def textproxy_available() -> bool:
    """True if textproxy binary is on PATH."""
    return shutil.which("textproxy") is not None


def textproxy_running() -> bool:
    """True if localhost:7474 is responding (quick socket check, <100ms timeout)."""
    try:
        with socket.create_connection(("localhost", 7474), timeout=0.1):
            return True
    except (OSError, TimeoutError):
        return False


# --- launch helpers ----------------------------------------------------------

def resume_cmd(session_id: str, session_name: str, profile: str, env: dict[str, str], claude_cmd_tpl: str = "claude") -> list[str]:
    """Return the argv list to resume a Claude session.

    Handles tmux window rename and profile-based claude command selection.
    Always returns a fish command so that fish functions are available.

    Tier 1 (textaccounts): CLAUDE_CONFIG_DIR is in env → use plain "claude".
    Tier 2 (custom commands): claude_cmd_tpl has {profile} → expands to e.g. "claude-work".
    Tier 3 (single account): claude_cmd_tpl is "claude" → uses "claude".
    """
    import shlex

    if "CLAUDE_CONFIG_DIR" in env:
        base_cmd = "claude"
    else:
        base_cmd = claude_cmd_tpl.format(profile=profile or "default")

    claude_cmd = f"{base_cmd} --resume {shlex.quote(session_id)}"

    if os.environ.get("TMUX"):
        window_name = shlex.quote(session_name or session_id[:8])
        fish_cmd = f"tmux rename-window {window_name}; set -lx CLAUDE_RESUME_NAME {window_name}; {claude_cmd}"
    else:
        fish_cmd = claude_cmd

    return ["fish", "-c", fish_cmd]


def build_launch_env(profile: str, integrations_enabled: dict[str, bool]) -> dict[str, str]:
    """Build subprocess env dict with integrations applied.

    Tier 1: textaccounts installed + enabled → delegates to textaccounts.api.env_for_profile()
            to get the right env vars (currently CLAUDE_CONFIG_DIR).
    Tier 2/3: no textaccounts → env is unchanged, resume_cmd handles command selection.
    """
    env = os.environ.copy()

    if integrations_enabled.get("textaccounts", True) and _HAS_TEXTACCOUNTS:
        if textaccounts_available():
            try:
                profile_env = _ta_env_for_profile(profile)
                env.update(profile_env)
            except ValueError:
                pass  # profile not found in textaccounts — fall through to tier 2/3

    if integrations_enabled.get("textproxy", True):
        if textproxy_available() and textproxy_running():
            env["ANTHROPIC_BASE_URL"] = "http://localhost:7474"

    return env
