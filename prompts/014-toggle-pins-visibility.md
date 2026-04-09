---
id: "014"
title: "TUI: y key toggles pinned sessions visibility"
repo: textsessions
phase: "phase-1"
model: sonnet
budget_usd: 1.00
max_turns: 20
depends_on: ["011"]
---

## Context

Pinned sessions always float to the top of the list. Sometimes users want to
hide them entirely (e.g. when they want to focus on recent non-pinned work
without the pinned items taking up space). A simple toggle, on by default,
handles this cleanly.

## Task

### 1. Add `_show_pinned` reactive in `tui/app.py`

```python
_show_pinned: reactive[bool] = reactive(True)
```

### 2. Filter pinned sessions in `_apply_filter`

After existing filters, if `_show_pinned` is False, exclude pinned sessions:

```python
if not self._show_pinned:
    self._filtered = [s for s in self._filtered if not s.pinned]
```

### 3. Add `y` binding

```python
Binding("y", "toggle_pins", "Pins"),
```

### 4. Add action

```python
def action_toggle_pins(self) -> None:
    self._show_pinned = not self._show_pinned
    self._apply_filter()
    self._populate_table()
    state = "visible" if self._show_pinned else "hidden"
    self.notify(f"Pinned sessions {state}", severity="information")
```

### 5. Update scope label or footer to reflect state

When `_show_pinned` is False, add a visual hint. The simplest approach: append
`[no pins]` to the scope label text in `watch__repo_filter` — or add a separate
`watch__show_pinned` that updates the same label:

```python
def watch__show_pinned(self, value: bool) -> None:
    self._update_scope_label()

def watch__repo_filter(self, value: str) -> None:
    self._update_scope_label()

def _update_scope_label(self) -> None:
    try:
        label = self.query_one("#scope-label", Label)
        repo_part = self._repo_filter or "all repos"
        pin_part = "" if self._show_pinned else "  [dim red]pins hidden[/dim red]"
        label.update(f"[dim]{repo_part}[/dim]{pin_part}")
    except NoMatches:
        pass
```

Replace the existing `watch__repo_filter` body with a call to
`_update_scope_label()`.

### 6. Update `HelpModal.HELP_ROWS` in `modals.py`

Add the new binding to the help table:

```python
("y", "Toggle pinned visibility"),
```

### 7. Tests

Add a test that:
- Creates sessions with and without `pinned: True`
- Verifies pinned sessions appear when `_show_pinned=True`
- Verifies pinned sessions are excluded when `_show_pinned=False`

(Test via `filter_sessions` + the new flag, not via the TUI widget.)

Actually the toggle is in `_apply_filter` in the TUI, so test at the app level
or just test manually. No unit test required — keep it simple.
