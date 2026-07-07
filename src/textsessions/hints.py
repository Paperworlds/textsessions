"""Read-only consumer for the textsessions-hints spec.

Producers (textprompts, etc.) write small YAML files at
``~/.cache/textsessions/hints/<session-uuid>.yaml`` to annotate Claude Code
sessions with persona, owner, and labels. textsessions reads them during
indexing and surfaces the fields in CLI/TUI views.

This module is the only place in textsessions that touches the hint
directory. Callers should treat hints as best-effort: missing, empty, or
malformed files yield ``None`` without raising.

# SPEC: textsessions-hints
"""

from __future__ import annotations

from pathlib import Path

import yaml

# SPEC: textsessions-hints
HINT_DIR = Path("~/.cache/textsessions/hints").expanduser()


def read_hint(session_id: str, hint_dir: Path | None = None) -> dict | None:
    """Return the hint dict for *session_id*, or ``None`` if absent/invalid.

    *hint_dir* override is only for tests; production code uses ``HINT_DIR``.

    # SPEC: textsessions-hints
    """
    if not session_id:
        return None
    base = hint_dir or HINT_DIR
    path = base / f"{session_id}.yaml"
    if not path.exists():
        return None
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(data, dict):
        return None
    return data
