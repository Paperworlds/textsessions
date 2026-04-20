---
id: "002"
title: "Split scan-ghosts into subfunctions"
repo: "textsessions"
model: "sonnet"
depends_on: []
budget_usd: 1.50
---

# 002 — Split scan-ghosts into subfunctions

## Goal

`scan_ghosts` in `src/textsessions/cli.py` is a single function of ~155 lines
handling five distinct modes: `--keep`, `--keep-all`, `--archive`/`--discard`,
and `--delete`. Split the mode bodies into private subfunctions so the main
command is a thin dispatcher.

## Current structure (lines ~528-683)

```
scan_ghosts(...)
  if keep_prefix:       # ~20 lines
      ...
      return
  if do_keep_all:       # ~25 lines
      ...
      return
  # dry-run report      # ~25 lines
  if as_json: ...
  ...
  if not flagged: return
  if do_delete: ...     # ~15 lines
  if do_archive or do_discard: ...  # ~25 lines
```

## What to do

Extract each mode into a private helper. Suggested names:

- `_scan_ghosts_keep(all_sessions, keep_prefix)` — `--keep` mode
- `_scan_ghosts_keep_all(all_sessions, repo_label)` — `--keep-all` mode
- `_scan_ghosts_report(flagged, by_repo, as_json, console)` — dry-run report section
- `_scan_ghosts_delete(flagged, yes, console)` — `--delete` mode
- `_scan_ghosts_archive(flagged, repo_label, do_discard, console)` — `--archive`/`--discard` mode

The main `scan_ghosts` click command becomes a dispatcher that calls these.

Each helper should be a plain function that receives exactly what it needs —
no access to `config` or click context, only the pre-computed data.

## Constraints

- No behaviour change whatsoever — same output, same exit codes, same mutations
- Keep all imports local (inside the helpers) as they are now
- No new tests required (existing behaviour is unchanged; helpers are internal)

## Verification

- `pytest` passes
- `ts scan-ghosts` (dry-run) still works on the real config
- `ts scan-ghosts --archive --repo textsessions` still works
