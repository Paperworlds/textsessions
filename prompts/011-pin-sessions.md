---
id: "011"
title: "Pin sessions: float to top within repo"
repo: textsessions
phase: "phase-1"
model: sonnet
budget_usd: 1.00
max_turns: 30
depends_on: ["002"]
---

## Context

Users want to mark specific sessions as "pinned" so they always appear at the top
of the list when browsing their repo — regardless of sort mode (date or priority).
Pinned sessions should still respect active filters (if a pinned session is filtered
out by text search or repo filter, it disappears normally).

Key binding: `x` (toggle pin/unpin on the selected session).

## Task

### 1. Add `pinned` field to `Session` in `sessions.py`

```python
@dataclass
class Session:
    ...
    pinned: bool = False
```

Update `_sessions_from_index` to read it:
```python
pinned=bool(entry.get("pinned", False)),
```

### 2. Add `do_pin` to `indexer.py`

```python
def do_pin(index: dict, session_id: str, pinned: bool) -> dict:
    """Set or clear the pinned flag on a session."""
    entry = index.setdefault(session_id, {})
    if pinned:
        entry["pinned"] = True
    else:
        entry.pop("pinned", None)
    return index
```

Export it from `indexer.py`.

### 3. Update sort to respect `pinned`

In `sessions.py`, update `sort_by_priority` to float pinned sessions to the top:
```python
def sort_by_priority(sessions: list[Session]) -> list[Session]:
    return sorted(sessions, key=lambda s: (not s.pinned, s.priority_order, s.last_active))
```

Also update the default `last_active` sort in `load_sessions` to put pinned first:
```python
all_sessions.sort(key=lambda s: (not s.pinned, s.last_active), reverse=True)
```

Wait — `reverse=True` on a tuple with `not s.pinned` (False/True) would put pinned
last. Use a two-key sort instead:
```python
all_sessions.sort(key=lambda s: (0 if s.pinned else 1, s.last_active), reverse=False)
# Then reverse only the last_active part by negating or re-sorting:
```

Actually: sort pinned first (ascending by pin=False/True), then by last_active descending:
```python
all_sessions.sort(key=lambda s: (not s.pinned, s.last_active), reverse=False)
```
This puts pinned=False (i.e. `not False = True` = 1) after pinned=True (= 0),
and within each group sorts by `last_active` ascending — but we want descending for
`last_active`. Use a helper:

```python
all_sessions.sort(key=lambda s: (not s.pinned, s.last_active))
# Then reverse only non-pinned by doing:
pinned = [s for s in all_sessions if s.pinned]
rest = sorted([s for s in all_sessions if not s.pinned], key=lambda s: s.last_active, reverse=True)
all_sessions = pinned + rest
```

And pinned sessions themselves sorted by last_active descending:
```python
pinned = sorted([s for s in all_sessions if s.pinned], key=lambda s: s.last_active, reverse=True)
rest = sorted([s for s in all_sessions if not s.pinned], key=lambda s: s.last_active, reverse=True)
all_sessions = pinned + rest
```

Apply the same pattern in `sort_by_priority`.

### 4. Add pin action in `tui/app.py`

Add binding:
```python
Binding("x", "pin_session", "Pin"),
```

Add action:
```python
def action_pin_session(self) -> None:
    s = self._current_session()
    if not s:
        return
    try:
        key = repo_key(s.repo_path)
        index = load_index(key)
        sid = resolve_session_id(index, s.id)
        index = do_pin(index, sid, not s.pinned)
        save_index(key, index)
        write_legacy_tsv(key, index)
        self._reload_sessions()
        self._populate_table()
        verb = "Pinned" if not s.pinned else "Unpinned"
        self.notify(verb, severity="information")
    except Exception as e:
        self.notify(f"Pin failed: {e}", severity="error")
```

Import `do_pin` from `..indexer`.

### 5. Visual indicator in the table

In `_populate_table`, prefix the name with `[pin]` marker for pinned sessions:
```python
if s.pinned:
    name_cell = f"[bold cyan]▶[/bold cyan] {s.name}"
elif s.is_ghost:
    name_cell = f"[dim]~{s.name}[/dim]"
elif s.is_orphan:
    ...
```

Choose a character that is unambiguous and compact. `▶` or `★` work well.

### 6. Tests

Add a test:
- Create a session entry in a YAML index with `pinned: True`
- Load sessions and assert the pinned session is first in the list
- Call `do_pin(index, sid, False)` and assert `pinned` key is removed from index
