---
id: "003"
title: "Fix resume from TUI; new session with name and priority"
repo: textsessions
model: sonnet
budget_usd: 3.00
max_turns: 80
depends_on: ["002"]
---

## Context

Two related features around launching Claude Code sessions from the TUI.

### Why resume is currently broken

`app.py` builds the command as:

```python
binary = "claude" if profile == "default" else f"claude-{profile}"
cmd = [binary, "--resume", resume_id]
subprocess.run(cmd)
```

Two bugs:

1. `claude-personal`, `claude-work` etc. are **fish shell functions**, not
   binaries. `subprocess.run` does not go through fish, so they are not found.

2. `self.suspend()` from Textual may not fully restore terminal state for
   Claude Code's interactive session (needs verification).

The correct invocation is:

```python
cmd = ["claude", "--my-profile", profile, "--resume", resume_id]
```

`--my-profile` is a valid but undocumented flag that switches Claude Code's
config directory. Confirmed working: `claude --my-profile personal --help`
runs without error.

For `profile == "default"` just omit `--my-profile` entirely.

### New session feature

`claude` accepts `-n / --name <name>` which sets a display name for the
session (shown in `/resume` picker and terminal title). We can use this to
pre-name a session at launch time.

Priority is our own metadata — it must be written to the YAML index *after*
the session is created, by detecting which session ID was just created.

## Task

### 1. Fix resume in `app.py`

Replace the broken binary derivation with:

```python
cmd = ["claude", "--resume", resume_id]
if profile != "default":
    cmd = ["claude", "--my-profile", profile, "--resume", resume_id]
```

Verify `self.suspend()` works correctly. If it does not restore the terminal
cleanly, wrap the subprocess call with:

```python
import os, sys
with self.suspend():
    subprocess.run(cmd, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr)
```

### 2. `NewSessionModal` in `modals.py`

New modal triggered by `n` key:

```
┌─ New session ──────────────────┐
│ Name (optional):               │
│ [____________________________] │
│                                │
│ Priority:  [ H0 | 1 | 2 | 3 ] │
│                                │
│      [Launch]    [Cancel]      │
└────────────────────────────────┘
```

Returns `NewSessionResult(name: str, priority: str, profile: str)` or `None`.
Profile is pre-filled from the repo of the currently selected session (or the
first configured repo as fallback).

### 3. Launch new session in `app.py`

Binding: `n` → `action_new_session`

Flow:

1. Push `NewSessionModal`, get `NewSessionResult`.
2. Record `launch_time = datetime.utcnow()`.
3. Build command:
   ```python
   cmd = ["claude"]
   if result.profile != "default":
       cmd += ["--my-profile", result.profile]
   if result.name:
       cmd += ["--name", result.name]
   ```
4. Run with `self.suspend()`.
5. After subprocess exits, call `_apply_post_launch_metadata(result, launch_time)`.

### 4. Post-launch metadata: `indexer.py`

Add `find_session_created_after(repo_key: str, since: datetime) -> str | None`:

- Load the YAML index for `repo_key`.
- Return the session ID whose `last_active` is >= `since` and that was not
  present in the index before launch (compare against a snapshot taken in
  step 2 above).
- If exactly one new session is found, return its ID.
- If zero or multiple, return `None` (ambiguous — skip metadata application).

In `app.py`, `_apply_post_launch_metadata`:

```python
def _apply_post_launch_metadata(self, result: NewSessionResult, since: datetime) -> None:
    # Re-scan to pick up the new session the indexer wrote
    self._reload_sessions()
    sid = find_session_created_after(repo_key(result.repo_path), since)
    if sid and result.priority:
        do_priority(repo_key(result.repo_path), sid, result.priority)
    self._reload_sessions()
    self._populate_table()
```

Note: `name` is already set via `--name` at launch; no post-launch name
mutation needed.

### 5. Tests

- `tests/test_resume.py` — parametrise over profiles: assert the correct
  `claude` command is built for `default`, `personal`, `work`.
- `tests/test_new_session.py` — unit test `find_session_created_after` with
  a synthetic YAML fixture that has one pre-existing and one post-launch entry.

## Notes

- If `--my-profile` ever breaks, fall back to checking whether a
  `claude-<profile>` executable exists on PATH before trying it, but do not
  use fish functions.
- `find_session_created_after` is best-effort. If it can't find the new
  session unambiguously, silently skip — the user can always set priority
  manually in the TUI after launch.
- The `NewSessionModal` profile selector should only show profiles that have
  at least one repo configured.
