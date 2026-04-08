---
id: "001"
title: "Ghost session detection, archive and delete"
repo: textsessions
model: sonnet
budget_usd: 3.00
max_turns: 80
depends_on: []
---

## Context

`textsessions` lists Claude Code sessions from YAML indexes in
`~/.local/state/claude-sessions/<repo-key>.yaml`.

A **ghost session** is one that should be hidden or removed because it's noise.
There are two flavours:

1. **Repo ghost** — the repo directory no longer exists on disk (deleted,
   moved, or renamed). The YAML key can't be reversed to a valid path.
   Known complication: the key is produced by `str(path).replace("/", "-")`,
   which is lossy when path components contain hyphens (e.g.
   `claude-context-proxy` → ambiguous). Detection must attempt the reversal
   and check `.exists()` *and* `(path / ".git").exists()`.

2. **Orphan session** — the repo exists but the session has no name, no tags,
   no priority, and a slug that looks like a throwaway test (short, single
   message, never returned to). These are clutter from quick ad-hoc tests.

Both should be detectable automatically and hideable/deleteable from the TUI.

## Discovered data (2026-04-08)

Running a scan against `~/.local/state/claude-sessions/`:

- `-Users-projects-paradigm-mono.yaml` — 338 sessions, ~206 auto-named with
  no metadata. Many are one-liners ("hello sir", "test test", "there",
  "testing proxy again"). These are the primary target for cleanup.
- All repo paths check out (no fully-dead repos). The
  `claude-context-proxy` key resolves to
  `/Users/projects/personal/claude-context-proxy` which exists.

## Task

### 1. Ghost detection in `sessions.py`

Add an `is_ghost` property to `Session`:

```python
@property
def is_ghost(self) -> bool:
    return not (self.repo_path / ".git").exists()
```

Add an `is_orphan` property — heuristic for throwaway sessions:
- name is just the ID prefix (≤8 chars, no spaces)
- no tags, no priority
- slug word count ≤ 8 words (very short first message)

### 2. Indexer: `textsessions scan-ghosts`

New CLI command that scans all configured repos, identifies ghost and orphan
sessions, and prints a report grouped by repo:

```
mono (338 sessions)
  [orphan]  70bbf240  2026-04-07  "test test"
  [orphan]  1cbb682c  2026-04-07  "there"
  [orphan]  29afd619  2026-04-07  "hello sir"
  ... (N more)
  Summary: 3 ghosts, 47 orphans

Total: 3 ghosts, 47 orphans across 5 repos
```

Options:
- `--repo <label>` — limit to one repo
- `--json` — machine-readable output
- `--dry-run` (default) / `--delete` — actually remove from YAML (writes back)
- `--min-words <n>` — orphan slug threshold (default: 8)

When `--delete` is passed, confirm with a `[y/N]` prompt unless `--yes` is given.

The command must call `claude-sessions-index delete <key> <id>` for each
session to remove, falling back to direct YAML mutation if the CLI is
unavailable.

### 3. TUI: archive/hide in `app.py` and `modals.py`

**Keybinding:** `d` → `action_archive_session`

**ArchiveModal** offers two choices:
- **Hide** (soft) — tags the session with `archived` via
  `claude-sessions-index tag`. The session is then filtered out by default.
- **Delete** (hard) — calls `claude-sessions-index delete <key> <id>`,
  then reloads.

**Filter change:** `filter_sessions` gains `show_archived: bool = False`.
When `False`, sessions with `"archived"` in their tags are excluded.

**Ghost indicator in table:** sessions where `is_ghost` or `is_orphan` is
True get a `[dim]` row style and a `~` prefix on the name column to signal
they're candidates for cleanup.

**`G` key:** toggle "ghosts only" view — equivalent to filtering to sessions
where `is_ghost or is_orphan`. Useful for batch-reviewing clutter before
running `scan-ghosts --delete`.

### 4. Tests

Add to `tests/`:
- `test_ghost_detection.py` — unit tests for `is_ghost` and `is_orphan`
  using tmp dirs and synthetic YAML fixtures
- `test_scan_ghosts.py` — CLI integration test invoking `scan-ghosts
  --json --dry-run` against a fixture STATE_DIR

## Notes

- Do NOT delete anything without explicit `--delete` + confirmation.
- The key→path reversal is lossy. When in doubt, mark as "possibly ghost"
  rather than "definitely ghost". Never auto-delete a possibly-ghost repo.
- `claude-sessions-index` may not support `delete` yet — implement YAML
  fallback so the feature works regardless.
- Keep `scan-ghosts` fast: it only reads YAML, no subprocess calls in
  dry-run mode.
