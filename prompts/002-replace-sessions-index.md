---
id: "002"
title: "Port claude-sessions-index into textsessions; archive-first UX"
repo: textsessions
model: sonnet
budget_usd: 4.00
max_turns: 120
depends_on: ["001"]
---

## Context

`textsessions` currently depends on an external local script
`~/.local/bin/claude-sessions-index` for all index mutations (tag, untag,
rename, priority) and for building the YAML session indexes from raw `.jsonl`
files. This is a hard local dependency we want to eliminate.

The script's full source is embedded in the repo at
`.files/reference/claude-sessions-index.py` (copy it there before starting).
Read it carefully — it contains the indexer logic, slug/name generation,
legacy TSV migration, and all mutation commands.

**Goal:** move that logic into `textsessions` as first-class code, expose it
via new CLI subcommands, and update all callers. The external script becomes
a thin backwards-compat shim.

## Architecture after this prompt

```
textsessions/
  indexer.py       ← ported from claude-sessions-index (scan, build, slug)
  cli.py           ← new subcommands: build, tag, untag, rename, priority, tags
  tui/app.py       ← call internal functions instead of subprocess
```

`claude-sessions-index` → symlink or wrapper to `textsessions index <cmd>`

## Task

### 1. Copy reference source

Copy `~/.local/bin/claude-sessions-index` to
`.files/reference/claude-sessions-index.py` so it's tracked in the repo.

### 2. `textsessions/indexer.py`

Port the following from the reference script into a new module:

- `make_slug(s, max_len)` — clean and truncate a string into a display slug
- `make_completion_name(s)` — slugified name for tab-completion
- `scan_sessions(pairs)` — walk `.jsonl` files, extract user messages +
  timestamps + custom titles. `pairs` is `["<claude_dir>::<sessions_dir>", ...]`
- `build_index(repo_key, pairs)` — rebuild YAML index, preserving existing
  priority/tags from old index. Write YAML to STATE_DIR.
- `write_legacy_tsv(repo_key, index)` — keep TSV for fish tab-completion
- Mutation functions: `do_tag`, `do_untag`, `do_priority`, `do_rename`,
  `do_tags` — operate on a loaded index dict, return updated dict.
  Keep `resolve_session_id` as a helper.
- `load_index(repo_key)` / `save_index(repo_key, index)` — thin wrappers
  around STATE_DIR YAML read/write (already partially in sessions.py;
  consolidate here).

All functions must be importable and testable without subprocess.

### 3. New CLI subcommands in `cli.py`

Add a `index` subcommand group:

```
textsessions index build <repo-key> <dir::path> [<dir::path> ...]
textsessions index tag   <repo-key> <session-prefix> <tag1,tag2>
textsessions index untag <repo-key> <session-prefix> <tag1,tag2>
textsessions index rename <repo-key> <session-prefix> <new title>
textsessions index priority <repo-key> <session-prefix> [H0|1|2|3|clear]
textsessions index tags  <repo-key>
textsessions index delete <repo-key> <session-id>
```

These commands must be drop-in compatible with the existing
`claude-sessions-index` CLI (same arg order, same output format) so the
fish functions that call it continue to work unchanged.

### 4. Update TUI callers

In `tui/app.py`, replace all `subprocess.run([SESSIONS_INDEX, ...])` calls
with direct calls to the indexer functions imported from `textsessions.indexer`.
No more subprocess for mutations.

The `SESSIONS_INDEX = "claude-sessions-index"` constant can be removed.

### 5. Backwards-compat shim

Create `scripts/claude-sessions-index` — a minimal shell script:

```sh
#!/bin/sh
exec textsessions index "$@"
```

Add it to pyproject.toml scripts so it gets installed:

```toml
[project.scripts]
textsessions = "textsessions.cli:main"
claude-sessions-index = "textsessions.cli:sessions_index_compat"
```

Where `sessions_index_compat` is a thin Click command that translates the
old positional-arg style (`<cmd> <repo-key> [args]`) into the new subcommand
style. This means the existing fish functions need zero changes.

### 6. Fix `scan-ghosts` archive behaviour (gap from prompt 001)

`scan-ghosts` currently only supports `--delete` (hard remove). This
contradicts the archive-first principle. Fix it:

- Default action (no flags): dry-run report, no mutations.
- `--archive` (new): tags each flagged session with `archived` via the
  indexer's `do_tag` function. Sessions disappear from normal view but
  are recoverable. This should be the recommended cleanup path.
- `--delete`: hard remove from YAML, as before. Requires `--yes` or
  interactive confirmation. Should warn that this is irreversible.

Update the help text to make `--archive` the suggested action:

```
textsessions scan-ghosts            # dry-run, shows report
textsessions scan-ghosts --archive  # recommended: hide ghosts/orphans
textsessions scan-ghosts --delete --yes  # permanent, use with care
```

### 7. Archive-first UX (fix from prompt 001)

The `ArchiveModal` added in prompt 001 must default to **archive (hide)**:
- Pressing `Enter` or `Space` in the modal confirms archive, not delete.
- "Delete" requires explicitly clicking/selecting the Delete button.
- Modal title should read: `Archive session? (d=archive  D=delete)`

Update `app.py` binding:
- `d` → archive (soft, default)
- `D` (shift+d) → delete directly with a short "Delete? [y/N]" confirm
  inline (no modal needed — it's intentional and irreversible).

### 7. Tests

- `tests/test_indexer.py` — unit tests for `make_slug`, `make_completion_name`,
  `scan_sessions` (with synthetic `.jsonl` fixtures), `build_index`,
  and all mutation functions.
- Update `tests/test_scan_ghosts.py` to import from `textsessions.indexer`
  instead of patching `STATE_DIR` globally.

## Notes

- The key→path reversal ambiguity (hyphens in dir names) is a known
  limitation. Do not try to fix it here — document it in a `# TODO` comment
  in `indexer.py`.
- Preserve the legacy TSV writes (`write_legacy_tsv`) for fish
  tab-completion backward compat.
- Keep `delete_session_from_index` in `sessions.py` or move it to
  `indexer.py` — either is fine, just don't duplicate it.
- Do NOT touch the actual `.jsonl` files — we only ever mutate the YAML index.
