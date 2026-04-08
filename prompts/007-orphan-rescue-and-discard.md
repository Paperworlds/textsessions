---
id: "007"
title: "Orphan rescue (--keep) and bulk archive (--discard) for scan-ghosts"
repo: textsessions
phase: "phase-1"
model: sonnet
budget_usd: 1.00
max_turns: 30
depends_on: ["005"]
---

## Context

`scan-ghosts` detects orphans by hex-hash name. Two missing operations:

1. **Rescue** — a session has a hex name but is real work. User wants to
   permanently exclude it from future orphan detection.
2. **Discard** — user wants to archive all currently detected orphans in one
   shot without reviewing them one by one.

## Task

### 1. `keep` tag in `is_orphan`

Add `"keep"` to the tag guard in `is_orphan`:

```python
@property
def is_orphan(self) -> bool:
    if self.tags or self.priority:
        return False
    return bool(_HEX_NAME_RE.match(self.name))
```

Since `"keep"` is a tag, it's already guarded — no code change needed here.
The convention is: tagging a session `keep` makes `is_orphan` return False.

Document this in a comment above `is_orphan`.

### 2. `scan-ghosts --keep <prefix>`

New option: tag one session as `keep`.

```
textsessions scan-ghosts --repo mono --keep ac4b7
```

- Resolves `<prefix>` to a session ID using `resolve_session_id` from `indexer.py`.
- Calls `do_tag(repo_key, session_id, "keep")`.
- Prints confirmation: `Kept: ac4b71c7  'hello sir | how much...'`
- `--repo` is required when using `--keep`.

### 3. `scan-ghosts --discard`

Archive all currently detected orphans (and ghosts) in one shot:

```
textsessions scan-ghosts --repo mono --discard
```

- Equivalent to `--archive` but skips the dry-run prompt.
- Prints count: `Archived 12 orphans in mono.`
- Can be combined with `--repo` to limit scope.
- Does NOT require `--yes` (archiving is reversible).

### 4. Tests

- `test_keep_tag_excludes_orphan` — hex-named session tagged `keep` → not orphan
- `test_scan_ghosts_keep` — CLI `--keep` tags the session and prints confirmation
- `test_scan_ghosts_discard` — CLI `--discard` archives all detected orphans
