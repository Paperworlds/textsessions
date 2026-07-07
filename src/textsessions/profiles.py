"""Profile and integration detection helpers for textsessions.

Profile resolution:
  - textaccounts installed + configured → CLAUDE_CONFIG_DIR is injected into
    the env via textaccounts.api.env_for_profile. The launched `claude`
    process picks up the right profile config.
  - Otherwise → plain `claude` with no profile switching (single account).

Never auto-installs anything — only detects and guides.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
import socket

# --- textaccounts integration (optional dependency) --------------------------
# All textaccounts knowledge is delegated to its public API. textsessions never
# reads ~/.textaccounts/ directly — that's textaccounts' business.

# SPEC: textaccounts-api-v0-2
try:
    from textaccounts.api import (
        active_profile as _ta_active_profile,         # SPEC: textaccounts-api-v0-2
        available as textaccounts_available,           # SPEC: textaccounts-api-v0-2
        env_for_profile,                               # SPEC: textaccounts-api-v0-2
        get_profile_lineage as _ta_get_profile_lineage,  # SPEC: textaccounts-api-v0-2
        list_profiles as list_textaccounts_profiles,  # SPEC: textaccounts-api-v0-2
        profile_description as _ta_profile_description,  # SPEC: textaccounts-api-v0-2
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

    def _ta_get_profile_lineage(name: str) -> dict | None:  # type: ignore[misc]
        return None


def active_profile() -> str | None:
    """Return the name of the currently active textaccounts profile, or None."""
    try:
        return _ta_active_profile()  # SPEC: textaccounts-api-v0-2
    except Exception:
        return None


def profile_description(name: str) -> str:
    """Return the textaccounts description for a profile, or empty string."""
    try:
        return _ta_profile_description(name)  # SPEC: textaccounts-api-v0-2
    except Exception:
        return ""


def get_profile_lineage(name: str) -> dict | None:
    """Return shallow-clone lineage for a profile, or None if unknown.

    Keys: shallow (bool), parent (str | None), ephemeral (bool), owner (str).
    Wraps the textaccounts.api function so callers can stay inside textsessions.profiles.
    """
    if not name:
        return None
    try:
        return _ta_get_profile_lineage(name)  # SPEC: textaccounts-api-v0-2
    except Exception:
        return None


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
    if not textaccounts_available():  # SPEC: textaccounts-api-v0-2
        raise click.UsageError(
            "textaccounts is installed but not configured. Run: textaccounts init"
        )
    known = list_textaccounts_profiles()  # SPEC: textaccounts-api-v0-2
    if name not in known:
        available = ", ".join(known) if known else "(none)"
        raise click.UsageError(
            f"Profile '{name}' not found in textaccounts. Available: {available}"
        )


# --- git profile helpers -----------------------------------------------------

_GIT_PROFILES_DIR = Path.home() / ".config" / "textsessions" / "git-profiles"


def write_git_profile_gitconfig(git_profile: "GitProfile") -> Path:
    """Write (or update) a per-identity gitconfig and return its path.

    Only writes if content changed, to avoid unnecessary mtime churn.
    """
    from .config import GitProfile  # local import to avoid circular

    _GIT_PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    out = _GIT_PROFILES_DIR / f"{git_profile.name}.gitconfig"

    lines = [
        "[include]",
        '\tpath = ~/.gitconfig',
        "",
        "[user]",
        f"\tname = {git_profile.display_name}",
        f"\temail = {git_profile.email}",
    ]
    if git_profile.signing_key:
        lines += [f"\tsigningkey = {git_profile.signing_key}"]
    lines += [
        "",
        "[commit]",
        "\tgpgsign = true",
        "[tag]",
        "\tgpgsign = true",
    ]
    content = "\n".join(lines) + "\n"

    if not out.exists() or out.read_text() != content:
        out.write_text(content)

    return out


# --- launch helpers ----------------------------------------------------------

def resume_cmd(
    session_id: str,
    session_name: str,
    profile: str,
    env: dict[str, str],
    *,
    window_label: str = "",
    checkpoint_log_path: "Path | None" = None,
) -> list[str]:
    """Return the argv list to resume a Claude session.

    Profile selection happens via `env` (textaccounts injects CLAUDE_CONFIG_DIR);
    this function always invokes plain `claude`. Wrapped in `fish -c` so the
    optional tmux window rename runs in the same shell.

    *window_label*: override for the tmux window name. When set (e.g. by
    ``ts jump <repo>``), it replaces the session-name-derived label so the
    tmux pane reflects the repo the user asked for. Profile suffix still
    applied. Empty falls back to the legacy session-name-prefix behaviour.
    """
    import shlex

    claude_cmd = f"claude --resume {shlex.quote(session_id)}"

    if checkpoint_log_path is not None:
        from .checkpoint import CHECKPOINT_SYSTEM_PROMPT
        claude_cmd += f" --append-system-prompt {shlex.quote(CHECKPOINT_SYSTEM_PROMPT)}"

    if os.environ.get("TMUX"):
        if window_label:
            # Caller-supplied label is taken verbatim — they already chose what
            # they want to see in the pane list, no profile suffix needed.
            base_label = window_label
            suffix = ""
        else:
            base_label = (session_name or session_id)[:8]
            suffix = f"-{profile[0]}" if profile else ""
        window_name = shlex.quote(f"{base_label}{suffix}")
        fish_cmd = f"tmux rename-window {window_name}; set -lx CLAUDE_RESUME_NAME {window_name}; {claude_cmd}"
    else:
        fish_cmd = claude_cmd

    return ["fish", "-c", fish_cmd]


def build_launch_env(
    profile: str,
    integrations_enabled: dict[str, bool],
    git_profile: "GitProfile | None" = None,
    *,
    force_no_proxy: bool = False,
) -> dict[str, str]:
    """Build subprocess env dict with integrations applied.

    textaccounts (when installed and enabled) injects CLAUDE_CONFIG_DIR via
    env_for_profile; otherwise env is unchanged and `claude` runs against the
    user's default config.

    git_profile, when given, writes a per-identity gitconfig and sets
    GIT_CONFIG_GLOBAL, overriding whatever textaccounts may have injected.

    force_no_proxy, when True, guarantees a direct-to-Anthropic session: the
    textproxy URL is never injected and any ANTHROPIC_BASE_URL inherited from
    the parent shell is stripped. Use for launches that need features Anthropic
    disables behind a non-Anthropic base URL (e.g. Claude Code Remote Control).
    Note this differs from merely disabling the textproxy integration, which
    only skips *setting* the URL and leaves an inherited one in place.
    """
    env = os.environ.copy()

    is_token_profile = False
    if integrations_enabled.get("textaccounts", True) and _HAS_TEXTACCOUNTS:
        if textaccounts_available():  # SPEC: textaccounts-api-v0-2
            try:
                profile_env = env_for_profile(profile)  # SPEC: textaccounts-api-v0-2
                env.update(profile_env)
                is_token_profile = "CLAUDE_CODE_OAUTH_TOKEN" in profile_env
            except ValueError:
                pass  # profile not found in textaccounts — fall through to tier 2/3

    if force_no_proxy:
        # Direct-to-Anthropic override — drop any inherited or injected base URL.
        env.pop("ANTHROPIC_BASE_URL", None)
    elif integrations_enabled.get("textproxy", True) and not is_token_profile:
        if textproxy_running():
            env["ANTHROPIC_BASE_URL"] = textproxy_url(profile)
        else:
            env.pop("ANTHROPIC_BASE_URL", None)
    elif is_token_profile:
        # Token-auth profiles go direct to Anthropic — remove any proxy URL that
        # may have been inherited from the parent shell environment.
        env.pop("ANTHROPIC_BASE_URL", None)

    if git_profile is not None:
        gc_path = write_git_profile_gitconfig(git_profile)
        env["GIT_CONFIG_GLOBAL"] = str(gc_path)

    return env
