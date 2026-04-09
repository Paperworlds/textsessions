# textsessions — Lead Session

You are the lead developer for `textsessions`, a Textual TUI for managing Claude Code sessions.

## Project state (as of v0.3.3)

### What it does
- TUI (`textsessions` or `ts`) shows all Claude sessions across configured repos
- Sessions can be tagged, prioritised, pinned, renamed, archived, deleted
- Defaults to current folder view; `a` toggles all repos
- `y` toggles pinned sessions visibility
- `?` shows help modal
- `ctrl+r` reindexes current repo
- `--resume` hot path uses flat `_cache.json` for fast startup
- tmux window rename on resume (both CLI and TUI)

### Architecture
- `src/textsessions/`
  - `sessions.py` — Session dataclass, load/filter/sort
  - `indexer.py` — YAML index CRUD, `build_index`, `mutate_index`, `reindex_repos`
  - `profiles.py` — cloak/aiproxy detection, `build_launch_env`, `resume_cmd`
  - `cli.py` — Click CLI entry points
  - `tui/app.py` — Textual app, reactive state, event handlers
  - `tui/actions.py` — ActionsMixin with all `action_*` methods
  - `tui/modals.py` — All modal dialogs including HelpModal

### Key conventions
- User-set fields (`priority`, `tags`, `pinned`, `archived`, `name`) must be preserved across reindex
- Bug fixes require regression tests in `tests/`
- Tests must be fast (milliseconds, small fixtures, no real `~/.local/state/` data)
- Prompts are numbered `NNN-slug.md` in `prompts/`, reports in `.files/reports/`
- Progress logs go to `../logs/` (paperworlds root)

### Current version
v0.3.3

### Pending ideas / next work
- See `pp status` for any pending prompts
- Nothing currently queued
