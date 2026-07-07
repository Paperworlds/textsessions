"""Per-session structured YAML audit log.

textsessions creates the file before spawning, injects TS_CHECKPOINT_LOG
into the session's env, and appends a trailer after exit. The session
appends checkpoint blocks voluntarily based on the injected system prompt.

# SPEC: textsessions-checkpoint
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .sessions import Session

# SPEC: textsessions-checkpoint
CHECKPOINT_DIR = Path.home() / ".local" / "state" / "textsessions" / "checkpoints"

CHECKPOINT_SYSTEM_PROMPT = (
    "You have access to a structured audit log at the path in the environment variable "
    "TS_CHECKPOINT_LOG. Append a YAML checkpoint block at natural decision points — "
    "when a phase completes, before a risky or irreversible action, when you hit a "
    "blocker, or when you change direction. Start each block with --- on its own line, "
    "then include: checkpoint (incrementing int starting at 1), timestamp (ISO-8601 UTC), "
    "summary (one paragraph describing what just completed or was decided), and optionally "
    "phase (str), references (list of {path:} or {url:, note:}), issues (list of strings), "
    "next (str — intended next action). Never re-read the file."
)


def checkpoint_log_path(session_id: str, checkpoint_dir: Path | None = None) -> Path:
    """Return the checkpoint log path for *session_id*."""
    base = checkpoint_dir or CHECKPOINT_DIR
    return base / f"{session_id}.yaml"


def has_checkpoint_log(session_id: str, checkpoint_dir: Path | None = None) -> bool:
    """Return True if a checkpoint log exists for *session_id*."""
    return checkpoint_log_path(session_id, checkpoint_dir).exists()


def write_checkpoint_header(path: Path, session: "Session") -> None:
    """Create *path* with the header YAML document.

    # SPEC: textsessions-checkpoint
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "checkpoint_log: '0.1.0'",
        f"session_id: {session.id}",
        f"started: '{now}'",
    ]
    if session.repo_label:
        lines.append(f"repo: {session.repo_label}")
    if session.persona:
        lines.append(f"persona: {session.persona}")
    if session.name and session.name != session.id[:8]:
        lines.append(f"task: {session.name}")
    path.write_text("\n".join(lines) + "\n")


def write_checkpoint_trailer(path: Path, exit_code: int | None = None) -> None:
    """Append the trailer YAML document to *path*.

    # SPEC: textsessions-checkpoint
    """
    if not path.exists():
        return
    now = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "---",
        "trailer: true",
        f"ended: '{now}'",
    ]
    if exit_code is not None:
        lines.append(f"exit_code: {exit_code}")
    with path.open("a") as f:
        f.write("\n".join(lines) + "\n")
