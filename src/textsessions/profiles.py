"""Profile and integration detection helpers for textsessions.

Detects textaccounts and ai-proxy at runtime.
Never auto-installs anything — only detects and guides.
"""

from __future__ import annotations

import os
import shutil
import socket
from pathlib import Path

_TEXTACCOUNTS_CONFIG = Path.home() / ".textaccounts" / "profiles.yaml"


def _textaccounts_config_path() -> Path:
    """Return the textaccounts config path (overridable in tests via module attr)."""
    return _TEXTACCOUNTS_CONFIG


def textaccounts_available() -> bool:
    """True if ~/.textaccounts/profiles.yaml exists."""
    return _textaccounts_config_path().exists()


def textaccounts_profile_dir(profile: str) -> Path | None:
    """Return the path for the named profile from ~/.textaccounts/profiles.yaml, or None."""
    config_path = _textaccounts_config_path()
    if not config_path.exists():
        return None
    try:
        import yaml
        with config_path.open() as f:
            data = yaml.safe_load(f) or {}
        entry = (data.get("profiles") or {}).get(profile)
        if entry is None:
            return None
        p = Path(entry["path"])
        return p if p.exists() else p  # return even if not yet created
    except Exception:
        return None


def list_textaccounts_profiles() -> list[str]:
    """Return profile names from ~/.textaccounts/profiles.yaml."""
    config_path = _textaccounts_config_path()
    if not config_path.exists():
        return []
    try:
        import yaml
        with config_path.open() as f:
            data = yaml.safe_load(f) or {}
        return sorted((data.get("profiles") or {}).keys())
    except Exception:
        return []


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


def resume_cmd(session_id: str, session_name: str, profile: str, env: dict[str, str], claude_cmd_tpl: str = "claude") -> list[str]:
    """Return the argv list to resume a Claude session.

    Handles tmux window rename and profile-based claude command selection.
    Always returns a fish command so that fish functions are available.

    claude_cmd_tpl: command template from config (e.g. "claude" or "claude-{profile}").
    {profile} is substituted with the session profile. CLAUDE_CONFIG_DIR takes
    precedence and always uses plain "claude".
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
    """Build subprocess env dict with textaccounts and ai-proxy integrations applied.

    Args:
        profile: The profile name from repo config.
        integrations_enabled: Dict with 'textaccounts' and 'aiproxy' bool values
                              (from IntegrationsConfig).

    Returns:
        A copy of os.environ with any integration env vars injected.
    """
    env = os.environ.copy()

    # textaccounts: set CLAUDE_CONFIG_DIR when textaccounts is available and
    # the profile is registered.
    if integrations_enabled.get("textaccounts", True):
        if textaccounts_available():
            d = textaccounts_profile_dir(profile)
            if d is not None:
                env["CLAUDE_CONFIG_DIR"] = str(d)

    # ai-proxy: inject ANTHROPIC_BASE_URL when proxy is detected as running.
    if integrations_enabled.get("aiproxy", True):
        if aiproxy_available() and aiproxy_running():
            env["ANTHROPIC_BASE_URL"] = "http://localhost:7474"

    return env
