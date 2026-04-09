# Report: 005 — Smarter orphan detection using hex-hash name pattern
Date: 2026-04-08T00:00:00Z
Status: DONE

## Changes
- 1f19090 Replace slug word-count orphan heuristic with hex-hash name pattern (textsessions)

## Test results
- textsessions: 80 tests passed

## Notes for next prompt
- `is_orphan` now matches names like `c5796`, `ac4b7`, `f68e2` (5-8 lowercase hex chars) with no tags/priority
- `scan-ghosts --min-words` option removed; `scan-ghosts` now delegates directly to `s.is_orphan`
- Orphan detection now correctly handles long-slug throwaways and rejects meaningful short names like `pp`, `ws-internal`, `prdx-admin`
