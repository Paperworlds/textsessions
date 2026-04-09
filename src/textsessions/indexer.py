"""Session indexer — ported from claude-sessions-index.

Builds and mutates YAML indexes of Claude Code sessions.
State dir: ~/.local/state/claude-sessions/<repo-key>.yaml

# TODO: The repo-key ↔ path conversion is lossy — hyphens in directory names
# are indistinguishable from path separators in the key. This is a known
# limitation and is not fixed here.
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import yaml

STATE_DIR = Path.home() / ".local" / "state" / "claude-sessions"
# Legacy paths for migration / backward compat
LEGACY_PRIORITY_DIR = Path.home() / ".claude-work" / "session-priority"
LEGACY_INDEX_DIR = Path.home() / ".claude-work" / "session-index"


# ---------------------------------------------------------------------------
# Slug helpers
# ---------------------------------------------------------------------------

def make_slug(s: str, max_len: int = 50) -> str:
    """Clean and truncate a string into a display slug."""
    s = re.sub(r"<[^>]+>", "", s)
    s = s.strip().replace("\n", " ")
    s = re.sub(r"\s+", " ", s)
    s = re.sub(
        r"^(?:hey |hi |please |can (?:we|you|i) |could (?:we|you|i) "
        r"|i need to |i want to |let's |we need to )+",
        "",
        s,
        flags=re.I,
    )
    if len(s) > max_len:
        s = s[:max_len].rsplit(" ", 1)[0] + "..."
    return s


def make_completion_name(s: str) -> str:
    """Return a slugified name suitable for fish tab-completion."""
    s = re.sub(r"<[^>]+>", "", s)
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")[:60]
    return s


# ---------------------------------------------------------------------------
# Index persistence
# ---------------------------------------------------------------------------

def load_index(repo_key: str) -> dict:
    """Load YAML index for repo_key. Returns {} if not found."""
    path = STATE_DIR / f"{repo_key}.yaml"
    if path.exists():
        with open(path) as f:
            return yaml.safe_load(f) or {}
    return {}


def save_index(repo_key: str, index: dict) -> None:
    """Write YAML index for repo_key to STATE_DIR."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = STATE_DIR / f"{repo_key}.yaml"
    with open(path, "w") as f:
        yaml.safe_dump(index, f, default_flow_style=False, sort_keys=False, width=120)


# ---------------------------------------------------------------------------
# Legacy TSV (fish tab-completion)
# ---------------------------------------------------------------------------

def write_legacy_tsv(repo_key: str, index: dict) -> None:
    """Write TSV index for fish tab-completion backward compat."""
    LEGACY_INDEX_DIR.mkdir(parents=True, exist_ok=True)
    path = LEGACY_INDEX_DIR / f"{repo_key}.tsv"
    seen_names: dict[str, int] = {}
    with open(path, "w") as f:
        for sid, entry in index.items():
            name = entry["name"]
            if name in seen_names:
                seen_names[name] += 1
                name = f"{name}-{seen_names[name]}"
            else:
                seen_names[name] = 1
            f.write(f"{name}\t{sid}\t{entry['profile']}\t{entry['last_active']}\t{entry['slug']}\n")


def _update_legacy_priority(repo_key: str, sid: str, level: str) -> None:
    """Keep the old priority TSV in sync."""
    LEGACY_PRIORITY_DIR.mkdir(parents=True, exist_ok=True)
    path = LEGACY_PRIORITY_DIR / f"{repo_key}.tsv"
    lines: list[str] = []
    if path.exists():
        lines = [ln for ln in open(path) if not ln.startswith(f"{sid}\t")]
    if level != "clear":
        lines.append(f"{sid}\t{level}\n")
    with open(path, "w") as f:
        f.writelines(lines)


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------

def scan_sessions(pairs: list[str]) -> list[dict]:
    """Scan .jsonl files and return raw session data.

    pairs: list of "<claude_dir>::<sessions_dir>" strings.
    Returns list of dicts sorted by last_ts descending.
    """
    sessions = []
    for pair in pairs:
        claude_dir, sessions_dir = pair.split("::")
        profile = os.path.basename(claude_dir)
        for path in glob.glob(f"{sessions_dir}/*.jsonl"):
            user_msgs: list[str] = []
            last_ts = ""
            custom_title = ""
            try:
                for line in open(path):
                    d = json.loads(line)
                    ts = d.get("timestamp", "")
                    if ts:
                        last_ts = ts
                    if d.get("type") == "custom-title":
                        custom_title = d.get("customTitle", "")
                    if d.get("type") == "user":
                        c = d.get("message", {}).get("content", "")
                        if isinstance(c, list):
                            c = " ".join(
                                x.get("text", "")
                                for x in c
                                if isinstance(x, dict) and x.get("type") != "tool_result"
                            )
                        c = str(c).strip().replace("\n", " ")
                        if (
                            c.startswith("<")
                            or c.startswith("Output ONLY")
                            or c.startswith("/")
                            or c.startswith("# Task:")
                        ):
                            continue
                        if c:
                            user_msgs.append(c)
            except (json.JSONDecodeError, OSError):
                continue
            if user_msgs and last_ts:
                combined = " | ".join(user_msgs[:3])
                full_sid = os.path.basename(path).replace(".jsonl", "")
                sessions.append({
                    "id": full_sid,
                    "last_ts": last_ts,
                    "profile": profile,
                    "combined": combined,
                    "custom_title": custom_title,
                })
    sessions.sort(key=lambda x: x["last_ts"], reverse=True)
    return sessions


# ---------------------------------------------------------------------------
# Build index
# ---------------------------------------------------------------------------

def _migrate_legacy_priorities(repo_key: str, index: dict) -> None:
    """Import priorities from old TSV file into the YAML index."""
    legacy = LEGACY_PRIORITY_DIR / f"{repo_key}.tsv"
    if not legacy.exists():
        return
    for line in open(legacy):
        parts = line.strip().split("\t")
        if len(parts) == 2:
            sid, pri = parts
            if sid in index and not index[sid].get("priority"):
                index[sid]["priority"] = pri


def build_index(repo_key: str, pairs: list[str]) -> dict:
    """Rebuild YAML index from .jsonl files, preserving user-set fields."""
    old_index = load_index(repo_key)
    sessions = scan_sessions(pairs)
    new_index: dict = {}

    for s in sessions:
        sid = s["id"]
        ct = s["custom_title"]
        combined = s["combined"]

        if ct and len(ct) >= 20:
            slug = make_slug(ct, 40)
        elif ct:
            slug = ct + " | " + make_slug(combined, 50 - len(ct))
        else:
            slug = make_slug(combined, 60)

        name = make_completion_name(ct) if ct else sid[:5]
        if not name:
            continue

        prof = s["profile"].replace(".claude-", "").replace(".claude", "default")
        last_dt = datetime.fromisoformat(s["last_ts"]).strftime("%Y-%m-%d %H:%M")

        old = old_index.get(sid, {})
        entry: dict = {"name": name, "profile": prof, "last_active": last_dt, "slug": slug}

        if old.get("priority"):
            entry["priority"] = old["priority"]
        if old.get("tags"):
            entry["tags"] = old["tags"]
        if old.get("pinned"):
            entry["pinned"] = True

        new_index[sid] = entry

    # Migrate legacy priorities on first run
    if not old_index:
        _migrate_legacy_priorities(repo_key, new_index)

    save_index(repo_key, new_index)
    write_legacy_tsv(repo_key, new_index)

    from .sessions import CACHE_PATH
    if CACHE_PATH.exists():
        CACHE_PATH.unlink()

    return new_index


# ---------------------------------------------------------------------------
# Session ID resolution
# ---------------------------------------------------------------------------

def resolve_session_id(index: dict, prefix: str) -> str:
    """Resolve a short ID prefix or session name to a full session ID.

    Exits (sys.exit(1)) if no match found — mirrors the original CLI behaviour.
    """
    matches = [sid for sid in index if sid.startswith(prefix)]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        matches = [sid for sid, e in index.items() if e.get("name", "") == prefix]
    if not matches:
        matches = [sid for sid, e in index.items() if e.get("name", "").startswith(prefix)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) == 0:
        print(f"No session matching '{prefix}'", file=sys.stderr)
        sys.exit(1)
    # Multiple matches — pick most recent, warn
    by_recency = sorted(matches, key=lambda s: index[s].get("last_active", ""), reverse=True)
    pick = by_recency[0]
    print(
        f"  (warn: '{prefix}' matched {len(matches)} sessions, using most recent {pick[:8]})",
        file=sys.stderr,
    )
    return pick


# ---------------------------------------------------------------------------
# Mutation functions
# ---------------------------------------------------------------------------

def do_tag(index: dict, sid: str, tags_csv: str) -> dict:
    """Add tags to a session. Returns the (mutated) index."""
    new_tags = [t.strip() for t in tags_csv.split(",") if t.strip()]
    existing = index[sid].get("tags", [])
    merged = list(dict.fromkeys(existing + new_tags))
    index[sid]["tags"] = merged
    return index


def do_untag(index: dict, sid: str, tags_csv: str) -> dict:
    """Remove tags from a session. Returns the (mutated) index."""
    remove = {t.strip() for t in tags_csv.split(",") if t.strip()}
    existing = index[sid].get("tags", [])
    remaining = [t for t in existing if t not in remove]
    if remaining:
        index[sid]["tags"] = remaining
    else:
        index[sid].pop("tags", None)
    return index


def do_priority(index: dict, sid: str, level: str) -> dict:
    """Set or clear priority on a session. Returns the (mutated) index."""
    if level not in ("H0", "1", "2", "3", "clear", ""):
        raise ValueError(f"Invalid priority: {level} (use H0, 1, 2, 3, or clear)")
    entry = index[sid]
    if level == "clear" or level == "":
        entry.pop("priority", None)
    else:
        entry["priority"] = level
    return index


def do_rename(index: dict, sid: str, new_title: str, repo_key: str | None = None) -> dict:
    """Rename a session (update slug/name). Optionally appends custom-title to .jsonl.

    If repo_key is provided, attempts to append a custom-title entry to the
    .jsonl file so the rename survives a full index rebuild.
    Returns the (mutated) index.
    """
    entry = index[sid]
    entry["slug"] = make_slug(new_title, 60)
    entry["name"] = make_completion_name(new_title) or sid[:5]

    if repo_key is not None:
        # Try to find the .jsonl across all profiles and append custom-title
        for claude_dir in sorted(Path.home().glob(".claude*")):
            if claude_dir.is_symlink() or not claude_dir.is_dir():
                continue
            candidate = claude_dir / "projects" / repo_key / f"{sid}.jsonl"
            if candidate.exists():
                title_entry = json.dumps({"type": "custom-title", "customTitle": new_title})
                with open(candidate, "a") as f:
                    f.write(title_entry + "\n")
                break

    return index


def do_tags(index: dict) -> dict[str, int]:
    """Return a mapping of tag → count across the entire index."""
    counts: dict[str, int] = {}
    for entry in index.values():
        for t in entry.get("tags", []):
            counts[t] = counts.get(t, 0) + 1
    return counts


def do_pin(index: dict, session_id: str, pinned: bool) -> dict:
    """Set or clear the pinned flag on a session."""
    entry = index.setdefault(session_id, {})
    if pinned:
        entry["pinned"] = True
    else:
        entry.pop("pinned", None)
    return index


def delete_session(index: dict, sid: str) -> dict:
    """Remove a session from the index dict. Returns the (mutated) index."""
    index.pop(sid, None)
    return index


def reindex_repos(repos: list, claude_dirs: list[Path]) -> int:
    """Rebuild indexes for the given repos. Returns total session count."""
    from .config import repo_key
    total = 0
    for r in repos:
        rk = repo_key(r.path)
        pairs = [
            f"{cd}::{cd / 'projects' / rk}"
            for cd in claude_dirs
            if (cd / "projects" / rk).exists()
        ]
        if not pairs:
            continue
        index = build_index(rk, pairs)
        total += len(index)
    return total


def find_session_created_after(repo_key: str, since: datetime, known_ids: set[str]) -> str | None:
    """Find the single new session added to repo_key's index after `since`.

    known_ids: snapshot of session IDs that existed before launch.
    Returns the session ID if exactly one new session is found, else None.
    """
    index = load_index(repo_key)
    new_ids = []
    for sid, entry in index.items():
        if sid in known_ids:
            continue
        last_active_str = entry.get("last_active", "")
        if not last_active_str:
            continue
        try:
            last_active = datetime.strptime(last_active_str, "%Y-%m-%d %H:%M")
        except ValueError:
            continue
        if last_active >= since.replace(second=0, microsecond=0):
            new_ids.append(sid)
    if len(new_ids) == 1:
        return new_ids[0]
    return None
