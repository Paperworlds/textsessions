---
id: "005"
title: "Smarter orphan detection using hex-hash name pattern"
repo: textsessions
phase: "phase-1"
model: sonnet
budget_usd: 1.00
max_turns: 30
depends_on: ["002"]
---

## Context

The current `is_orphan` property in `sessions.py` uses a word-count heuristic on
the session slug (`len(slug.split()) <= 8`). This is too blunt: it misses real
throwaways whose slugs are long (e.g. `"hello sir | how much context did i use
this far?"`) and would catch legitimate work sessions with short names.

The correct signal is already in the data: **Claude auto-names sessions with a
5-8 character lowercase hex string** (e.g. `c5796`, `ac4b7`, `f68e2`). User-named
sessions have meaningful names (`pp`, `mcp`, `ws-internal`, `prdx-admin`).

## Task

### 1. Fix `is_orphan` in `sessions.py`

Replace the current heuristic with:

```python
import re

_HEX_NAME_RE = re.compile(r'^[0-9a-f]{5,8}$')

@property
def is_orphan(self) -> bool:
    if self.tags or self.priority:
        return False
    return bool(_HEX_NAME_RE.match(self.name))
```

Remove the old slug word-count logic entirely.

### 2. Update `scan-ghosts` CLI

Remove the `--min-words` option — it's no longer needed. Keep `--repo`,
`--archive`, `--delete`, `--yes`, `--json`.

Update the help text accordingly.

### 3. Update tests

- Update `tests/test_ghost_detection.py` orphan tests to reflect the new logic:
  - `c5796` (hex hash, no tags) → orphan
  - `ac4b7` (hex hash, tagged) → not orphan
  - `pp` (short meaningful name) → not orphan
  - `ws-internal` (hyphenated short name) → not orphan
  - `prdx-admin` → not orphan
- Remove any tests that relied on `--min-words`.
