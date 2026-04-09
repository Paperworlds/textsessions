# Report: 012 — TUI: ctrl+r to reindex current repo
Date: 2026-04-09T00:00:00Z
Status: DONE

## Changes
- a984dfc prompt 012: ctrl+r to reindex current repo from TUI (textsessions)

## Test results
- textsessions: 100 tests passed

## Notes for next prompt
- `reindex_repos()` is now importable from `textsessions.indexer` for any future reindex callers
- The TUI `action_reindex` respects the active `_repo_filter` (scoped to current repo or all repos)
- Recursive repos are expanded before reindexing via `_expand_recursive`
