# Report: 007 — Orphan rescue (--keep) and bulk archive (--discard) for scan-ghosts
Date: 2026-04-08T00:00:00Z
Status: DONE

## Changes
- fc239bd Add scan-ghosts --keep and --discard; document 'keep' tag in is_orphan (textsessions)

## What was done

### `sessions.py` — `is_orphan` documentation
Added a docstring block explaining that tagging a session `keep` makes `is_orphan` return False.
No code change was needed — the existing `if self.tags` guard already handles it.

### `cli.py` — `scan-ghosts --keep <prefix>`
- New option `--keep` takes a prefix string.
- Requires `--repo` (error if omitted).
- Searches loaded sessions for a matching ID or name prefix; uses first (most recent) match.
- Tags the session `keep` via `do_tag`, saves index, writes legacy TSV.
- Prints: `Kept: <short_id>  '<slug>'`

### `cli.py` — `scan-ghosts --discard`
- New flag `--discard` runs the same archive logic as `--archive` but skips the dry-run prompt.
- Can be combined with `--repo` to limit scope.
- When `--repo` is provided, prints: `Archived N orphans in <repo>.`
- Otherwise prints: `Archived N sessions.`

## Test results
- textsessions: 86 tests passed, 0 failed
  - test_keep_tag_excludes_orphan: PASS
  - test_scan_ghosts_keep: PASS
  - test_scan_ghosts_discard: PASS
  - All existing tests: PASS

## Notes for next prompt
- `--keep` resolves by ID prefix first, then name prefix. With ambiguous prefix it picks the most recent session (already sorted by last_active desc).
- `--discard` output says "orphans" (matching spec) only when `--repo` is specified; otherwise "sessions" for the multi-repo case.
