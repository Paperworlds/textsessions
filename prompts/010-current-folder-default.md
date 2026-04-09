---
id: "010"
title: "TUI: default to current folder view, A to show all"
repo: textsessions
phase: "phase-1"
model: sonnet
budget_usd: 1.00
max_turns: 30
depends_on: ["002"]
---

## Context

The TUI currently shows all sessions from all repos on startup. Users almost always
work in the context of one repo. A current-folder-first default reduces noise and
makes the most relevant sessions immediately visible.

There is already partial support: `config.ui.startup_repo = "current"` triggers
`_repo_for_cwd()` on mount, but the implementation conflates the repo filter with
the text search input (`_filter_query`), causing them to interfere.

## Task

### 1. Change the default to "current" in `config.py`

```python
@dataclass
class UiConfig:
    startup_repo: str = "current"  # was "all"
```

Also update the fallback in `load()` when the key is missing from TOML:
```python
startup_repo=ui_data.get("startup_repo", "current"),
```

### 2. Separate repo filter from text filter in `tui/app.py`

Add a new reactive:
```python
_repo_filter: reactive[str] = reactive("")
_cwd_repo_label: str = ""  # set once on mount, used for toggle
```

Update `_apply_filter` to pass `repo_label`:
```python
def _apply_filter(self) -> None:
    q = self._filter_query
    self._filtered = filter_sessions(
        self._sessions,
        query=q,
        repo_label=self._repo_filter,
        ghosts_only=self._ghosts_only,
    )
    if self._sort_by_priority:
        self._filtered = sort_by_priority(self._filtered)
```

### 3. Update `on_mount` to use `_repo_filter` instead of the text input

Replace the existing `startup_repo == "current"` block:
```python
def on_mount(self) -> None:
    self._reload_sessions()
    matched = _repo_for_cwd(self._config)
    if matched and self._config.ui.startup_repo == "current":
        self._cwd_repo_label = matched.label
        self._repo_filter = matched.label
        self._apply_filter()
    self._populate_table()
    ...
```

Do NOT set `inp.value` — the text input starts empty.

### 4. Add "A" binding to toggle between current repo and all

```python
Binding("a", "toggle_all", "All"),
```

```python
def action_toggle_all(self) -> None:
    if self._repo_filter:
        self._repo_filter = ""
    else:
        self._repo_filter = self._cwd_repo_label
    self._apply_filter()
    self._populate_table()
```

If `_cwd_repo_label` is empty (user is not inside any configured repo), "A" is
a no-op (no repo to return to).

### 5. Show current scope in the UI

Add a `Label` widget below the filter input showing current scope:

```
[all repos]   or   [textsessions]
```

Update it whenever `_repo_filter` changes. Bind a watch on `_repo_filter`:
```python
def watch__repo_filter(self, value: str) -> None:
    label = self.query_one("#scope-label", Label)
    label.update(f"[dim]{value or 'all repos'}[/dim]")
```

Add `Label("", id="scope-label")` to `compose()` inside the left panel,
between filter input and table.

### 6. Tests

No new tests needed — behaviour is UI-only. Verify existing tests still pass.
