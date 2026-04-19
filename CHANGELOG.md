# Changelog

## v0.8.6

- Fix: DuplicateKey crash when a parent repo and a child repo both index the same session ID
- `load_sessions` now deduplicates by session ID (last/child entry wins)
- `_populate_table` adds a second-layer guard so the TUI never raises DuplicateKey regardless of upstream state
- `action_reindex` now passes `all_repos` to `reindex_repos` so partial reindex (filtered to one repo) no longer incorrectly absorbs child repo sessions into the parent YAML

## v0.8.4

- tmux window names now prefix the profile's first letter: `w-pathfinder`, `p-refactor`
- Makes it easier to tell work/personal sessions apart at a glance in the tmux status bar

## v0.8.3

- Fix: rename no longer reverts after the next resume
- `do_rename` also updates `~/.claude*/sessions/<pid>.json` so Claude Code stops re-asserting the old launch `--name` as a fresh `custom-title` on every turn
- Previously: a session launched with `--name presync` would overwrite a rename to `pathfinder-upgrade` on the next resume — visible most on pinned sessions (resumed more often)

## v0.8.2

- Fix: rename in `ts view` now persists through `ts scan` rebuilds
- `build_index` stores `jsonl_path` in each entry; `do_rename` uses it directly (O(1)) instead of globbing `~/.claude*` dirs
- Fixes sessions launched from repo subdirectories whose `.jsonl` was never found by the old path search

## v0.8.1

- `f` key in TUI opens repo filter dropdown
- `--version` shows git commit hash (from package dir, not CWD)
- `TEXTPROXY_BASE_URL`/`TEXTPROXY_HOST`/`TEXTPROXY_PORT` constants + `textproxy_url()` helper
- textproxy profile URL set when proxy is running; stale `ANTHROPIC_BASE_URL` cleared when proxy is down
- `--current-folder` auto-reindex includes subdirectory sessions (no logic duplication)

## v0.8.0

Structured refactor pass — no behaviour changes.

- `STATE_DIR` defined once in `config.py`, imported everywhere (was duplicated in `indexer.py`)
- Dead code removed: `_HEX_RE` in `indexer.py` (same pattern lives in `sessions.py` as `_HEX_RE_NAME`)
- All inline/aliased imports in `cli.py` moved to module level; `prog_name="textsessions"` added to `--version`
- Config `load()` now validates repo entries (raises `ValueError` on missing `path`/`label` or wrong type)
- Dead overwritten variable removed in `discover_repos_for_dir`
- Shared `make_session()` factory in `tests/conftest.py` — was duplicated across 3 test files

**Tests — 151 passing, 1 skipped**

| Area | Coverage | Notes |
|---|---|---|
| CLI commands | high | `scan-ghosts` (dry-run, archive, delete, keep, discard), `index`, `filter`, `pin` via `CliRunner` |
| TUI app | medium | Startup, filter input, sort/pin/repo toggles, quit via Textual `Pilot` |
| Config | high | Load/save roundtrip, validation errors, repo key derivation |
| Session logic | high | Ghost/orphan detection, filter, sort, `keep` tag |
| Not covered | — | `action_resume_session`, `action_new_session` (shell out to `claude`/`fish`) |

## v0.7.2

- `--version` now shows git commit hash (from package dir, not CWD)
- `TEXTPROXY_HOST`, `TEXTPROXY_PORT`, `TEXTPROXY_BASE_URL` constants + `textproxy_url()` helper — no more hardcoded URLs
- textproxy profile URL now set whenever proxy is running, regardless of binary on PATH
- Fixed stale env-check workaround (root cause was in textproxy's `extractProfile`)

## v0.7.1

- `f` key in TUI opens a repo filter dropdown — pick any configured repo label to filter the session table, or "All repos" to clear
- `--current-folder` auto-reindex now uses `reindex_repos` with `all_repos` param — no logic duplication, subdirectory sessions included correctly

## v0.7.0

- Sessions from repo subdirectories (e.g. `features/branch`) now appear under the parent repo's index
- `--name` from `claude --name` at launch is picked up as session name (reads `~/.claude*/sessions/*.json` metadata)
- Closest-repo matching: subdirectory sessions are assigned to the most specific configured ancestor, preventing duplicates across nested repos
- Session deduplication safety net in scanner

## v0.6.3

- Profile prefix in textproxy base URL (`/p/<profile>`) — enables per-profile tagging in textproxy

## v0.6.2

- `--repo` is now optional in `textsessions new` — detects repo from current directory when omitted
- `ts`, `xts` aliases registered as Python entry points in pyproject (no more fish wrapper functions)

## v0.6.1

- `last_active` timestamp now included in session cache (`_cache.json`) — enables `tw status` active-today counts without scanning YAML files
- `--model/-m` option on `textsessions new` — passes through to `claude --model`
- Fix: priority modal crash (`Illegal select value False`) when YAML index had `priority: false`

## v0.6.0

- `textsessions new --repo REPO [--profile] [--name] [--model] [--priority]` — launch a new Claude session from the CLI
- Profile validation: `--profile` now errors if textaccounts is missing or the profile doesn't exist (no more silent fallback)
- Shell completions for `--repo` (repo labels) and `--profile` (textaccounts profiles) on the `new` command
- Fish aliases: `ts`/`xts` shorthand for `textsessions` (installed via `just install-completions`)

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
