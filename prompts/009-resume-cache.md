---
id: "009"
title: "Fast --resume via flat session cache"
repo: textsessions
phase: "phase-1"
model: sonnet
budget_usd: 1.00
max_turns: 30
depends_on: ["002"]
---

## Context

`textsessions sessions --resume <name>` is noticeably slow because `load_sessions(config)`
reads one YAML file per configured repo before it can find the matching session.
With many repos this adds perceptible startup latency for a very frequent operation.

## Goal

Reduce `--resume` startup to a single file read (from N YAML reads) by maintaining
a flat cache of all sessions.

## Task

### 1. Add a flat cache in `sessions.py`

Add `CACHE_PATH = STATE_DIR / "_cache.json"` (alongside the per-repo `.yaml` files).

Add helpers:
- `_cache_is_fresh() -> bool` — True if `_cache.json` exists and its mtime is ≥ the
  mtime of every `*.yaml` in `STATE_DIR`. Use `os.path.getmtime`.
- `_write_cache(sessions: list[Session]) -> None` — serialise sessions to JSON.
  Store only fields needed for `--resume`: `id`, `name`, `profile`, `repo_label`, `repo_path`.
- `_load_cache() -> list[Session]` — deserialise and reconstruct `Session` objects.
  Missing optional fields default to their dataclass defaults.
- `load_sessions_fast(config: Config) -> list[Session]` — if `_cache_is_fresh()`,
  return `_load_cache()`; otherwise call `load_sessions(config)`, write the cache,
  then return the result.

### 2. Use `load_sessions_fast` in the `--resume` path

In `cli.py`, in the `--resume` branch of `sessions_cmd`, replace:
```python
all_sessions = load_sessions(config)
```
with:
```python
all_sessions = load_sessions_fast(config)
```

Import `load_sessions_fast` alongside the existing `load_sessions` import.

### 3. Invalidate cache on reindex

In `cli.py` `reindex` command and in `indexer.py` `build_index`, after writing a
YAML index, delete `CACHE_PATH` (if it exists) so the next access rebuilds it.

```python
from .sessions import CACHE_PATH
if CACHE_PATH.exists():
    CACHE_PATH.unlink()
```

### 4. Tests

Add a test in `tests/` that:
- Writes two minimal YAML indexes
- Calls `load_sessions_fast` twice
- Asserts the second call loads from cache (check `_cache_is_fresh()` returns True)
- Touches a YAML file and asserts `_cache_is_fresh()` returns False

### 5. No change to `load_sessions` signature

`load_sessions` remains unchanged — it is used by the TUI which always wants a
fresh full load. Only the CLI `--resume` hot path uses the cache.
