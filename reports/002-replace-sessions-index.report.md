# Report: 002 — Port claude-sessions-index into textsessions; archive-first UX
Date: 2026-04-08T14:10:00Z
Status: DONE

## Changes
- 704df0c Port claude-sessions-index into textsessions; archive-first UX (textsessions)

## What was done

### indexer.py (new)
Full port of `~/.local/bin/claude-sessions-index` into `src/textsessions/indexer.py`:
- `make_slug`, `make_completion_name` — slug/name helpers
- `scan_sessions(pairs)` — scan .jsonl files, extract user messages + timestamps
- `build_index(repo_key, pairs)` — rebuild YAML index, preserve user-set fields (tags/priority)
- `write_legacy_tsv`, `_update_legacy_priority` — backward compat TSV writes
- `load_index`, `save_index` — thin YAML wrappers
- `resolve_session_id` — prefix/name resolution with sys.exit on no match
- `do_tag`, `do_untag`, `do_priority`, `do_rename`, `do_tags`, `delete_session` — mutation functions

### cli.py additions
- `textsessions index` subcommand group: build, tag, untag, rename, priority, tags, delete
- `sessions_index_compat` Click command — translates old `claude-sessions-index <cmd> <repo-key> [args]` style
- `scan-ghosts` rework: default = dry-run; `--archive` (recommended, reversible); `--delete` now requires `--yes`

### pyproject.toml
- Added `claude-sessions-index = "textsessions.cli:sessions_index_compat"` to `[project.scripts]`

### tui/app.py
- Removed `SESSIONS_INDEX = "claude-sessions-index"` constant
- Replaced all `subprocess.run([SESSIONS_INDEX, ...])` mutation calls with direct `indexer.*` function calls
- Added `action_delete_session_direct` (bound to `D`) — hard delete via `_DeleteConfirmModal`
- Binding: `d` → archive modal, `D` → inline delete confirm

### tui/modals.py
- `ArchiveModal` rework: archive-first (Enter/Space confirm archive); title reads "Archive session? (d=archive  D=delete)"; result values changed hide→archive
- New `_DeleteConfirmModal` for `D` binding — y/n confirm, warns irreversible

### tests
- `tests/test_indexer.py` — 31 unit tests covering all indexer functions, scan, build
- `tests/test_scan_ghosts.py` — added dry-run no-mutation test, `--archive` test, `--delete` requires `--yes` test

## Test results
- textsessions: 55 tests passed, 0 failed

## Notes for next prompt
- The key↔path reversal ambiguity (hyphens in dir names) is documented in indexer.py as a TODO
- `_DeleteConfirmModal` is prefixed with underscore as it's an internal detail
- `write_legacy_tsv` still writes to `~/.claude-work/session-index/` for fish tab-completion backward compat
- The external `~/.local/bin/claude-sessions-index` script can now be replaced with a `#!/bin/sh\nexec textsessions index "$@"` shim — but that's a deployment step, not code
