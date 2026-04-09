# Report: 009 — Fast --resume via flat session cache
Date: 2026-04-09T00:00:00Z
Status: DONE

## Changes
- 494e960 prompt 009: fast --resume via flat session cache (textsessions)

## Test results
- textsessions: 91 tests passed (5 new for cache, 86 pre-existing)

## Notes for next prompt
- `CACHE_PATH = STATE_DIR / "_cache.json"` is now public — usable by any future code that needs to bust the cache.
- Cache stores only `id`, `name`, `profile`, `repo_label`, `repo_path` — enough for `--resume` matching. `last_active` and `slug` are not cached; the full `load_sessions` path is still used for the TUI and table display.
- `_cache_is_fresh()` is mtime-based (no content hash) — fast and simple.
- Cache is invalidated both in `reindex` (cli.py) and inside `build_index` (indexer.py) to cover programmatic callers.
