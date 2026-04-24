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

# SPEC: textaccounts-api
try:
    from textaccounts.api import (
        active_profile as _ta_active_profile,         # SPEC: textaccounts-api
        available as textaccounts_available,           # SPEC: textaccounts-api
        env_for_profile,                               # SPEC: textaccounts-api
        list_profiles as list_textaccounts_profiles,  # SPEC: textaccounts-api
        profile_description as _ta_profile_description,  # SPEC: textaccounts-api
    )
    _HAS_TEXTACCOUNTS = True
except ImportError:
    _HAS_TEXTACCOUNTS = False

    def textaccounts_available() -> bool:  # type: ignore[misc]
        return False

    def list_textaccounts_profiles() -> list[str]:  # type: ignore[misc]
        return []

    def env_for_profile(name: str) -> dict[str, str]:  # type: ignore[misc]
        return {}

    def _ta_profile_description(name: str) -> str:  # type: ignore[misc]
        return ""

    def _ta_active_profile() -> str | None:  # type: ignore[misc]
        return None


def active_profile() -> str | None:
    """Return the name of the currently active textaccounts profile, or None."""
    try:
        return _ta_active_profile()  # SPEC: textaccounts-api
    except Exception:
        return None


def profile_description(name: str) -> str:
    """Return the textaccounts description for a profile, or empty string."""
    try:
        return _ta_profile_description(name)  # SPEC: textaccounts-api
    except Exception:
        return ""


# --- textproxy integration ---------------------------------------------------

TEXTPROXY_HOST = "localhost"
TEXTPROXY_PORT = 7474
TEXTPROXY_BASE_URL = f"http://{TEXTPROXY_HOST}:{TEXTPROXY_PORT}"


def textproxy_available() -> bool:
    """True if textproxy binary is on PATH."""
    return shutil.which("textproxy") is not None


def textproxy_running() -> bool:
    """True if textproxy is responding (quick socket check, <100ms timeout)."""
    try:
        with socket.create_connection((TEXTPROXY_HOST, TEXTPROXY_PORT), timeout=0.1):
            return True
    except (OSError, TimeoutError):
        return False


def textproxy_url(profile: str) -> str:
    """Return the ANTHROPIC_BASE_URL for the given profile."""
    return f"{TEXTPROXY_BASE_URL}/p/{profile}"


# --- profile validation ------------------------------------------------------

def validate_explicit_profile(name: str) -> None:
    """Raise click.UsageError if *name* can't be activated.

    Called only when ``--profile`` is explicitly passed on the CLI — silent
    fallback is not acceptable when the user asked for a specific profile.
    """
    import click

    if not _HAS_TEXTACCOUNTS:
        raise click.UsageError(
            f"Profile '{name}' requested but textaccounts is not installed.\n"
            "Install it (uv tool install textaccounts) or remove --profile."
        )
    if not textaccounts_available():  # SPEC: textaccounts-api
        raise click.UsageError(
            "textaccounts is installed but not configured. Run: textaccounts init"
        )
    known = list_textaccounts_profiles()  # SPEC: textaccounts-api
    if name not in known:
        available = ", ".join(known) if known else "(none)"
        raise click.UsageError(
            f"Profile '{name}' not found in textaccounts. Available: {available}"
        )


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
        base_label = (session_name or session_id)[:8]
        suffix = f"-{profile[0]}" if profile else ""
        window_name = shlex.quote(f"{base_label}{suffix}")
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
        if textaccounts_available():  # SPEC: textaccounts-api
            try:
                profile_env = env_for_profile(profile)  # SPEC: textaccounts-api
                env.update(profile_env)
            except ValueError:
                pass  # profile not found in textaccounts — fall through to tier 2/3

    if integrations_enabled.get("textproxy", True):
        if textproxy_running():
            env["ANTHROPIC_BASE_URL"] = textproxy_url(profile)
        else:
            env.pop("ANTHROPIC_BASE_URL", None)

    return env
