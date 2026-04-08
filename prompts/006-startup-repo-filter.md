---
id: "006"
title: "Config option: start TUI filtered to current repo or show all"
repo: textsessions
phase: "phase-1"
model: sonnet
budget_usd: 1.00
max_turns: 30
depends_on: ["002"]
---

## Context

When launching `textsessions` from inside a project directory, the user often
wants to see only that repo's sessions immediately. When launching from elsewhere
they want the full view. Currently there is no way to configure this.

## Task

### 1. Config option in `config.toml`

Add to `Config`:

```toml
[ui]
startup_repo = "current"   # "current" | "all" (default: "all")
```

- `"current"` — on startup, pre-filter to the repo whose path matches (or is a
  parent of) `$PWD`. If no repo matches, fall back to showing all.
- `"all"` — no pre-filter (current behaviour).

### 2. Apply in `app.py`

In `on_mount`, after `_populate_table`:

```python
if self._config.ui.startup_repo == "current":
    matched = _repo_for_cwd(self._config)
    if matched:
        self._filter_query = matched.label
        self._apply_filter()
```

Add `_repo_for_cwd(config) -> RepoConfig | None`:
- Walk `config.repos`, find the repo whose `path` is equal to or a parent of
  `Path.cwd()`.
- Return the closest match (longest matching prefix).

### 3. Tests

- `test_repo_for_cwd_match` — cwd inside a configured repo → returns that repo
- `test_repo_for_cwd_no_match` — cwd unrelated → returns None
- `test_repo_for_cwd_closest` — cwd inside nested repo → returns closest match
