---
id: "008"
title: "TUI error handling: toast notifications for failed actions"
repo: textsessions
phase: "phase-1"
model: sonnet
budget_usd: 1.00
max_turns: 30
depends_on: ["002"]
---

## Context

When actions fail silently (e.g. subprocess returns non-zero, session not found,
index write fails), the TUI gives no feedback. The user sees nothing or gets
errors printed to the terminal after the TUI exits.

Textual has a built-in `app.notify()` method that shows a toast notification
in the corner of the screen.

## Task

### 1. Wrap `action_resume_session` with error handling

```python
result = subprocess.run(cmd, env=env, ...)
if result.returncode != 0:
    self.notify(f"Resume failed (exit {result.returncode})", severity="error")
```

### 2. Wrap `action_new_session` post-launch

If `subprocess.run` returns non-zero, show a toast. Don't block on it.

### 3. Wrap index mutations

Tag, untag, rename, priority — if the indexer raises, catch and show a toast:

```python
try:
    do_tag(...)
    self.notify("Tagged", severity="information")
except Exception as e:
    self.notify(f"Tag failed: {e}", severity="error")
```

Success toasts for mutations are optional but nice — keep them brief (1-2 words).

### 4. Wrap `action_archive_session` and `action_delete_session_direct`

Same pattern — catch exceptions, show error toast. On success show
`"Archived"` / `"Deleted"` toast.

### 5. Tests

No new tests needed — toast behaviour is UI-only and hard to unit test.
Just verify existing tests still pass.
