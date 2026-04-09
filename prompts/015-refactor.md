---
id: "015"
title: "Refactor: index mutations, view refresh, preserved fields, app.py split"
repo: textsessions
phase: "phase-1"
model: sonnet
budget_usd: 2.00
max_turns: 30
depends_on: ["014"]
---

# Prompt 015 — Refactor

## Goal
Clean up technical debt accumulated across prompts 009–014. No new features.

## Tasks

### 1. Preserve all user-set fields across reindex

In `indexer.py` `build_index()`, the following fields from `old_index` must be
carried forward into `new_index` for each session that still exists:

- `priority` (already done)
- `tags` (already done)
- `pinned` (added in 014 fix, verify it's there)
- `archived` (currently missing — verify and add if absent)
- `name` (custom rename — if the user renamed a session, preserve it)

Pattern:
```python
old = old_index.get(sid, {})
for field in ("priority", "tags", "pinned", "archived", "name"):
    if old.get(field):
        entry[field] = old[field]
```

Add a test in `tests/` that builds an index twice and confirms all user-set
fields survive the second build.

### 2. Extract `mutate_index` helper

In `tui/app.py`, every mutation repeats:
```python
key = repo_key(s.repo_path)
index = load_index(key)
sid = resolve_session_id(index, s.id)
index = do_something(index, sid, ...)
save_index(key, index)
write_legacy_tsv(key, index)
```

Extract to `indexer.py`:
```python
def mutate_index(repo_key: str, session_id: str, fn) -> None:
    """Load index, resolve sid, apply fn(index, sid), save."""
    index = load_index(repo_key)
    sid = resolve_session_id(index, session_id)
    fn(index, sid)
    save_index(repo_key, index)
    write_legacy_tsv(repo_key, index)
```

Update all call sites in `app.py` to use it.

### 3. Merge `_apply_filter` + `_populate_table` into `_refresh_view`

Every call site in `app.py` calls both in sequence. Replace with a single
`_refresh_view()` method that calls `_apply_filter()` then `_populate_table()`.
Update all call sites.

### 4. Fix duplicated pinned-sort logic in `sessions.py`

`load_sessions` and `sort_by_priority` both implement pinned-first sorting.
Extract a single `_sort_sessions(sessions, by_priority=False)` helper and have
both call it.

### 5. Split `tui/app.py` action methods into a mixin

`app.py` is ~550 lines. Extract all `action_*` methods into
`tui/actions.py` as an `ActionsMixin` class. `SessionsApp` inherits from both
`App` and `ActionsMixin`.

Keep reactive state, compose/mount, event handlers, and `_*` helpers in `app.py`.

---

## Constraints
- No behaviour changes — refactor only
- All existing tests must still pass after each task
- Commit after each task (5 commits total)
- Do not add new public API beyond `mutate_index`

## Progress log
Write to `../logs/015-refactor.progress.log`.

## Report
Write to `.files/reports/015-refactor.report.md`.
