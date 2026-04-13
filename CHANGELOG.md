# Changelog

## v0.5.4

- `textsessions doctor` — validates integrations, tool availability, profile wiring, and session indexes in one command
- Fix: `just install` now includes `.[accounts]` extra — `textaccounts` was missing from the tool venv, silently breaking profile injection on resume
- Fix: reindex updates `name`/`description` when `/rename` custom title changes (was reverting to old name)
- Session ID (first 8 chars) shown in `textsessions sessions` table
- Config screen: Enter opens edit-label modal instead of doing nothing; subprocess flash documented in roadmap

## v0.5.3

- Rename `ai-proxy` → `textproxy` across codebase to match [paperworlds/textproxy](https://github.com/paperworlds/textproxy)
- Auto-rename: `reindex` now upgrades hex-stub session names when a `/rename` custom title exists in the `.jsonl`
- `textsessions sessions --reindex` — rebuild indexes from `.jsonl` before listing
- `--current-folder` already auto-reindexes the matched repo; `--reindex` covers all other repos
- TUI fix: filter input height restored to 3 rows (was broken at 1)

## v0.5.2

- `is_automated` property on Session — True for sessions tagged "worker" or "automated"
- `show_automated` param on `filter_sessions()` — automated sessions hidden by default
- Explicitly filtering `#worker` tag overrides the automated filter (shows them)

## v0.4.1

- `textsessions rename <name> <new title>` — rename a session by name with tab-completion
- `textsessions tag <name> <tags>` — add/remove tags by name (`-tag` prefix to remove); tab-completion on session name
- Sessions table: always shows **Name** first, then **Info** (description if set, otherwise slug)
- Fix: `y` (toggle pins visibility) now keeps pinned sessions in the list sorted by last-active, instead of removing them

## v0.4.0

- `textsessions search "query"` — AI-powered natural language search over session history
- `textsessions tree` — dump all repos and sessions as a YAML/JSON tree
- `textsessions index auto-rename` — rename hex-ID sessions using titles set via `/rename` in Claude
- Session `description` field — user-set label shown in TUI and session list, separate from the auto-generated slug
- Completion names shortened to 4 words max for cleaner tab completion
- Fish completions: added `search`, `tree`, `index auto-rename`, `reindex`, `index` subcommands
- Fix: `ai_search_profile` used as a full command (no double-prefix); wrapped in `fish -c` to resolve fish functions

## v0.3.4

- New session launched with `cwd` set to the session's repo
- Configurable `claude_cmd` template with `{profile}` substitution (e.g. `claude-{profile}` dispatches to fish functions)

## v0.3.3

- Refactor: extract `ActionsMixin` from TUI app; `_sort_sessions()` helper
- All user-set fields (`priority`, `tags`, `pinned`, `name`, `description`) are now explicitly preserved across `reindex`

## v0.3.2

- Fix: tmux window rename on TUI resume (was only working from CLI)
- Fix: `pinned` flag preserved across reindex

## v0.3.1

- `y` key toggles pinned sessions visibility in TUI

## v0.3.0

- `--resume` uses flat JSON cache (`_cache.json`) for fast startup
- TUI defaults to current repo on startup (`ui.startup_repo = "current"`)
- `a` key toggles between current-folder view and all repos
- `x` key pins sessions (float to top within repo)
- `ctrl+r` reindexes current repo from inside the TUI
- `?` shows full keybinding help modal

## v0.2.0

- tmux window rename on `--resume` (sets window name to session name)

## v0.1.x

- Initial release: Textual TUI, session list, resume, new session modal
- `scan-ghosts`: detect ghost (dead repo) and orphan (hex-named, no metadata) sessions
- `--archive`, `--discard`, `--keep`, `--keep-all` for bulk cleanup
- Cloak + ai-proxy profile integration (`textsessions profile` commands)
- `init --recursive`: scan a directory for all git repos
- `sessions --current-folder`: auto-filter to cwd repo
- Toast notifications for TUI action errors and successes
- Fish shell completions
