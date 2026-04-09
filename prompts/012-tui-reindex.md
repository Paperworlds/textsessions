---
id: "012"
title: "TUI: ctrl+r to reindex current repo"
repo: textsessions
phase: "phase-1"
model: sonnet
budget_usd: 1.00
max_turns: 20
depends_on: ["002"]
---

## Context

The TUI shows sessions loaded from YAML indexes. When new Claude sessions are
created in a repo, the index is not updated automatically — the user has to drop
to the terminal and run `textsessions reindex`. There is no way to trigger
a reindex from inside the TUI.

## Task

### 1. Extract reindex logic into a shared helper in `indexer.py`

The `reindex` CLI command duplicates the build logic inline. Extract it:

```python
def reindex_repos(repos: list[RepoConfig], claude_dirs: list[Path]) -> int:
    """Rebuild indexes for the given repos. Returns total session count."""
    from .config import repo_key
    total = 0
    for r in repos:
        rk = repo_key(r.path)
        pairs = [
            f"{cd}::{cd / 'projects' / rk}"
            for cd in claude_dirs
            if (cd / "projects" / rk).exists()
        ]
        if not pairs:
            continue
        index = build_index(rk, pairs)
        total += len(index)
    return total
```

Update the CLI `reindex` command to call `reindex_repos` instead of duplicating
the loop.

### 2. Add `ctrl+r` binding in `tui/app.py`

```python
Binding("ctrl+r", "reindex", "Reindex"),
```

### 3. Add `action_reindex` that reindexes the active scope

```python
def action_reindex(self) -> None:
    from ..config import detect_claude_dirs
    from ..indexer import reindex_repos
    # Reindex only the current repo filter if active, else all repos
    if self._repo_filter:
        repos = [r for r in self._config.repos if r.label == self._repo_filter or r.label.startswith(self._repo_filter + "/")]
    else:
        repos = list(self._config.repos)
    if not repos:
        self.notify("No repos to reindex", severity="warning")
        return
    try:
        self.notify("Reindexing…", severity="information")
        claude_dirs = detect_claude_dirs()
        count = reindex_repos(repos, claude_dirs)
        self._reload_sessions()
        self._populate_table()
        self.notify(f"Reindexed — {count} sessions", severity="information")
    except Exception as e:
        self.notify(f"Reindex failed: {e}", severity="error")
```

Note: `self._repo_filter` is introduced in prompt 010. If that prompt has not been
applied yet, replace `self._repo_filter` with `""` (always reindex all repos).

### 4. Expand recursive repos before reindexing

The `_config.repos` list may contain entries with `recursive=True` (parent dirs
that expand to multiple git repos). Expand them before passing to `reindex_repos`:

```python
from ..sessions import _expand_recursive
expanded = []
for r in repos:
    if r.recursive:
        expanded.extend(_expand_recursive(r))
    else:
        expanded.append(r)
repos = expanded
```

### 5. Tests

No new tests needed. Verify existing tests pass.
