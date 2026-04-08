#!/usr/bin/env python3
"""Claude sessions index manager.

Builds and queries a YAML index of Claude Code sessions.
Consolidates session metadata, priorities, and tags into one file per repo.

State dir: ~/.local/state/claude-sessions/<repo-key>.yaml

Usage (called by claude-sessions.fish):
    claude-sessions-index list <repo-key> [--limit N] [--filter STR] [--tag TAG] [--priority] <dir1::path1> ...
    claude-sessions-index tag <repo-key> <session-id-prefix> <tag1,tag2,...>
    claude-sessions-index untag <repo-key> <session-id-prefix> <tag1,tag2,...>
    claude-sessions-index tags <repo-key>
"""

import json
import glob
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import yaml

STATE_DIR = Path.home() / ".local" / "state" / "claude-sessions"
# Legacy paths for migration
LEGACY_PRIORITY_DIR = Path.home() / ".claude-work" / "session-priority"
# Keep writing the TSV index for tab-completion compatibility
LEGACY_INDEX_DIR = Path.home() / ".claude-work" / "session-index"


def make_slug(s, max_len=50):
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
        s = s[: max_len].rsplit(" ", 1)[0] + "..."
    return s


def make_completion_name(s):
    s = re.sub(r"<[^>]+>", "", s)
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")[:60]
    return s


def load_index(repo_key):
    path = STATE_DIR / f"{repo_key}.yaml"
    if path.exists():
        with open(path) as f:
            return yaml.safe_load(f) or {}
    return {}


def save_index(repo_key, index):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = STATE_DIR / f"{repo_key}.yaml"
    with open(path, "w") as f:
        yaml.safe_dump(index, f, default_flow_style=False, sort_keys=False, width=120)


def migrate_legacy_priorities(repo_key, index):
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


def resolve_session_id(index, prefix):
    """Resolve a short ID prefix or session name to a full session ID."""
    # Try ID prefix first
    matches = [sid for sid in index if sid.startswith(prefix)]
    if len(matches) == 1:
        return matches[0]
    # Try name match (exact or prefix)
    if not matches:
        matches = [sid for sid, e in index.items() if e.get("name", "") == prefix]
    if not matches:
        matches = [sid for sid, e in index.items() if e.get("name", "").startswith(prefix)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) == 0:
        print(f"No session matching '{prefix}'", file=sys.stderr)
        sys.exit(1)
    # Multiple matches: pick most recent, warn
    by_recency = sorted(matches, key=lambda s: index[s].get("last_active", ""), reverse=True)
    pick = by_recency[0]
    print(f"  (warn: '{prefix}' matched {len(matches)} sessions, using most recent {pick[:8]})", file=sys.stderr)
    return pick


def scan_sessions(pairs):
    """Scan jsonl files and return raw session data."""
    sessions = []
    for pair in pairs:
        claude_dir, sessions_dir = pair.split("::")
        profile = os.path.basename(claude_dir)
        for path in glob.glob(f"{sessions_dir}/*.jsonl"):
            user_msgs = []
            last_ts = ""
            custom_title = ""
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
                    if c.startswith("<") or c.startswith("Output ONLY") or c.startswith("/") or c.startswith("# Task:"):
                        continue
                    if c:
                        user_msgs.append(c)
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


def build_index(repo_key, pairs):
    """Rebuild index from jsonl files, preserving user-set fields (priority, tags)."""
    old_index = load_index(repo_key)
    sessions = scan_sessions(pairs)
    new_index = {}

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

        # Preserve user-set fields from old index
        old = old_index.get(sid, {})

        entry = {"name": name, "profile": prof, "last_active": last_dt, "slug": slug}

        # Preserve priority and tags
        if old.get("priority"):
            entry["priority"] = old["priority"]
        if old.get("tags"):
            entry["tags"] = old["tags"]

        new_index[sid] = entry

    # Migrate legacy priorities if this is first run
    if not old_index:
        migrate_legacy_priorities(repo_key, new_index)

    save_index(repo_key, new_index)

    # Write legacy TSV index for tab-completion
    write_legacy_tsv(repo_key, new_index)

    return new_index


def write_legacy_tsv(repo_key, index):
    """Write TSV index for fish tab-completion compatibility."""
    LEGACY_INDEX_DIR.mkdir(parents=True, exist_ok=True)
    path = LEGACY_INDEX_DIR / f"{repo_key}.tsv"
    seen_names = {}
    with open(path, "w") as f:
        for sid, entry in index.items():
            name = entry["name"]
            if name in seen_names:
                seen_names[name] += 1
                name = f"{name}-{seen_names[name]}"
            else:
                seen_names[name] = 1
            f.write(f"{name}\t{sid}\t{entry['profile']}\t{entry['last_active']}\t{entry['slug']}\n")


def cmd_list(repo_key, pairs, limit=10, filter_str="", tag_filter="", sort_by_priority=False):
    index = build_index(repo_key, pairs)

    PRIORITY_ORDER = {"H0": 0, "1": 1, "2": 2, "3": 3}
    display = []
    for sid, e in index.items():
        # Text filter
        if filter_str and filter_str not in e["slug"].lower():
            continue
        # Tag filter
        if tag_filter:
            tags = e.get("tags", [])
            if tag_filter not in tags:
                continue

        pri_val = PRIORITY_ORDER.get(e.get("priority", ""), 9)
        display.append((pri_val, e["last_active"], sid[:8], e["profile"], e["last_active"], e["slug"], sid, e.get("priority", ""), e.get("tags", [])))

    if sort_by_priority:
        display.sort(key=lambda x: (x[0], x[1]), reverse=True)
        display.sort(key=lambda x: x[0])

    shown = 0
    for pri_val, _, short_id, prof, last_dt, slug, full_sid, pri_lbl, tags in display:
        if shown >= limit:
            break
        # Priority badge
        if pri_lbl.startswith("H"):
            pri_badge = f"[{pri_lbl}] "
        elif pri_lbl:
            pri_badge = f"[P{pri_lbl}] "
        else:
            pri_badge = ""
        # Tag badges (at end of line)
        tag_str = "  " + " ".join(f"#{t}" for t in tags) if tags else ""
        print(f"  {short_id}  {pri_badge}[{prof}]  {last_dt}  {slug}{tag_str}")
        shown += 1


def cmd_tag(repo_key, prefix, tags_csv):
    index = load_index(repo_key)
    sid = resolve_session_id(index, prefix)
    new_tags = [t.strip() for t in tags_csv.split(",") if t.strip()]
    existing = index[sid].get("tags", [])
    merged = list(dict.fromkeys(existing + new_tags))  # preserve order, deduplicate
    index[sid]["tags"] = merged
    save_index(repo_key, index)
    print(f"  {sid[:8]}  tags: {', '.join(merged)}")


def cmd_untag(repo_key, prefix, tags_csv):
    index = load_index(repo_key)
    sid = resolve_session_id(index, prefix)
    remove = {t.strip() for t in tags_csv.split(",") if t.strip()}
    existing = index[sid].get("tags", [])
    remaining = [t for t in existing if t not in remove]
    if remaining:
        index[sid]["tags"] = remaining
    else:
        index[sid].pop("tags", None)
    save_index(repo_key, index)
    print(f"  {sid[:8]}  tags: {', '.join(remaining) if remaining else '(none)'}")


def cmd_priority(repo_key, prefix, level=""):
    """Set or show session priority."""
    index = load_index(repo_key)
    sid = resolve_session_id(index, prefix)
    entry = index[sid]

    if not level:
        pri = entry.get("priority", "")
        if pri.startswith("H"):
            badge = f"[{pri}]"
        elif pri:
            badge = f"[P{pri}]"
        else:
            badge = "[no priority]"
        print(f"  {sid[:8]}  {badge}  {entry['slug']}")
        return

    if level not in ("H0", "1", "2", "3", "clear"):
        print(f"Invalid priority: {level} (use H0, 1, 2, 3, or clear)", file=sys.stderr)
        sys.exit(1)

    if level == "clear":
        entry.pop("priority", None)
        print(f"  {sid[:8]}  [cleared]  {entry['slug']}")
    else:
        entry["priority"] = level
        badge = f"[{level}]" if level.startswith("H") else f"[P{level}]"
        print(f"  {sid[:8]}  {badge}  {entry['slug']}")

    # Also update legacy TSV for backward compat
    _update_legacy_priority(repo_key, sid, level)
    save_index(repo_key, index)


def _update_legacy_priority(repo_key, sid, level):
    """Keep the old priority TSV in sync."""
    LEGACY_PRIORITY_DIR.mkdir(parents=True, exist_ok=True)
    path = LEGACY_PRIORITY_DIR / f"{repo_key}.tsv"
    lines = []
    if path.exists():
        lines = [l for l in open(path) if not l.startswith(f"{sid}\t")]
    if level != "clear":
        lines.append(f"{sid}\t{level}\n")
    with open(path, "w") as f:
        f.writelines(lines)


def cmd_rename(repo_key, prefix, new_title):
    """Rename a session by updating its custom title in the jsonl and index."""
    index = load_index(repo_key)
    sid = resolve_session_id(index, prefix)
    entry = index[sid]

    # Find the jsonl file across all profiles
    jsonl_path = None
    for claude_dir in Path.home().glob(".claude*"):
        if claude_dir.is_symlink() or not claude_dir.is_dir():
            continue
        candidate = claude_dir / "projects" / repo_key / f"{sid}.jsonl"
        if candidate.exists():
            jsonl_path = candidate
            break

    if jsonl_path:
        # Append a custom-title entry so it persists across index rebuilds
        title_entry = json.dumps({"type": "custom-title", "customTitle": new_title})
        with open(jsonl_path, "a") as f:
            f.write(title_entry + "\n")

    # Update index immediately
    entry["slug"] = make_slug(new_title, 60)
    entry["name"] = make_completion_name(new_title) or sid[:5]
    save_index(repo_key, index)
    write_legacy_tsv(repo_key, index)
    print(f"  {sid[:8]}  → {entry['slug']}")


def cmd_tags(repo_key):
    """List all tags in use with counts."""
    index = load_index(repo_key)
    counts = {}
    for entry in index.values():
        for t in entry.get("tags", []):
            counts[t] = counts.get(t, 0) + 1
    if not counts:
        print("  No tags in use")
        return
    for tag, count in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
        print(f"  #{tag}  ({count})")


def main():
    if len(sys.argv) < 3:
        print("Usage: claude-sessions-index <command> <repo-key> [args...]", file=sys.stderr)
        sys.exit(1)

    cmd = sys.argv[1]
    repo_key = sys.argv[2]

    if cmd == "list":
        # Parse flags
        limit = 10
        filter_str = ""
        tag_filter = ""
        sort_by_priority = False
        pairs = []
        i = 3
        while i < len(sys.argv):
            arg = sys.argv[i]
            if arg == "--limit" and i + 1 < len(sys.argv):
                limit = int(sys.argv[i + 1])
                i += 2
            elif arg == "--filter" and i + 1 < len(sys.argv):
                filter_str = sys.argv[i + 1]
                i += 2
            elif arg == "--tag" and i + 1 < len(sys.argv):
                tag_filter = sys.argv[i + 1]
                i += 2
            elif arg == "--priority":
                sort_by_priority = True
                i += 1
            else:
                pairs.append(arg)
                i += 1
        cmd_list(repo_key, pairs, limit, filter_str, tag_filter, sort_by_priority)

    elif cmd == "tag":
        if len(sys.argv) < 5:
            print("Usage: claude-sessions-index tag <repo-key> <session-prefix> <tag1,tag2>", file=sys.stderr)
            sys.exit(1)
        cmd_tag(repo_key, sys.argv[3], sys.argv[4])

    elif cmd == "untag":
        if len(sys.argv) < 5:
            print("Usage: claude-sessions-index untag <repo-key> <session-prefix> <tag1,tag2>", file=sys.stderr)
            sys.exit(1)
        cmd_untag(repo_key, sys.argv[3], sys.argv[4])

    elif cmd == "rename":
        if len(sys.argv) < 5:
            print("Usage: claude-sessions-index rename <repo-key> <session-prefix> <new title>", file=sys.stderr)
            sys.exit(1)
        cmd_rename(repo_key, sys.argv[3], " ".join(sys.argv[4:]))

    elif cmd == "tags":
        cmd_tags(repo_key)

    elif cmd == "priority":
        if len(sys.argv) < 4:
            print("Usage: claude-sessions-index priority <repo-key> <session-prefix> [H0|1|2|3|clear]", file=sys.stderr)
            sys.exit(1)
        level = sys.argv[4] if len(sys.argv) > 4 else ""
        cmd_priority(repo_key, sys.argv[3], level)

    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
