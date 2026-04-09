"""Profile and integration detection helpers for textsessions.

Detects cloak (https://github.com/synth1s/cloak) and ai-proxy at runtime.
Never auto-installs anything — only detects and guides.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
from pathlib import Path


def cloak_available() -> bool:
    """True if cloak is installed (binary on PATH)."""
    return shutil.which("cloak") is not None


def cloak_profile_dir(profile: str) -> Path | None:
    """Return ~/.cloak/profiles/<profile> if it exists, else None."""
    d = Path.home() / ".cloak" / "profiles" / profile
    return d if d.exists() else None


def list_cloak_profiles() -> list[str]:
    """Return sorted list of profile names found in ~/.cloak/profiles/."""
    base = Path.home() / ".cloak" / "profiles"
    if not base.exists():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir())


def cloak_version() -> str | None:
    """Return cloak version string, or None if unavailable."""
    if not cloak_available():
        return None
    try:
        result = subprocess.run(
            ["cloak", "--version"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        line = (result.stdout or result.stderr).strip().splitlines()[0]
        return line if line else None
    except Exception:
        return None


def aiproxy_available() -> bool:
    """True if ai-proxy binary is on PATH."""
    return shutil.which("ai-proxy") is not None


def aiproxy_running() -> bool:
    """True if localhost:7474 is responding (quick socket check, <100ms timeout)."""
    try:
        with socket.create_connection(("localhost", 7474), timeout=0.1):
            return True
    except (OSError, TimeoutError):
        return False


def resume_cmd(session_id: str, session_name: str, profile: str, env: dict[str, str]) -> list[str]:
    """Return the argv list to resume a Claude session.

    Handles tmux window rename and profile-based claude command selection.
    Always returns a fish command so that fish functions (claude-<profile>) are available.
    """
    import shlex

    if profile and profile != "default" and "CLAUDE_CONFIG_DIR" not in env:
        claude_cmd = f"claude-{profile} --resume {shlex.quote(session_id)}"
    else:
        claude_cmd = f"claude --resume {shlex.quote(session_id)}"

    if os.environ.get("TMUX"):
        window_name = shlex.quote(session_name or session_id[:8])
        fish_cmd = f"tmux rename-window {window_name}; set -lx CLAUDE_RESUME_NAME {window_name}; {claude_cmd}"
    else:
        fish_cmd = claude_cmd

    return ["fish", "-c", fish_cmd]


def build_launch_env(profile: str, integrations_enabled: dict[str, bool]) -> dict[str, str]:
    """Build subprocess env dict with cloak and ai-proxy integrations applied.

    Args:
        profile: The profile name from repo config.
        integrations_enabled: Dict with 'cloak' and 'aiproxy' bool values
                              (from IntegrationsConfig).

    Returns:
        A copy of os.environ with any integration env vars injected.
    """
    env = os.environ.copy()

    # Cloak: set CLAUDE_CONFIG_DIR when profile is non-default and cloak is
    # available and the profile dir exists.
    if integrations_enabled.get("cloak", True) and profile != "default":
        if cloak_available():
            d = cloak_profile_dir(profile)
            if d is not None:
                env["CLAUDE_CONFIG_DIR"] = str(d)

    # ai-proxy: inject ANTHROPIC_BASE_URL when proxy is detected as running.
    if integrations_enabled.get("aiproxy", True):
        if aiproxy_available() and aiproxy_running():
            env["ANTHROPIC_BASE_URL"] = "http://localhost:7474"

    return env
