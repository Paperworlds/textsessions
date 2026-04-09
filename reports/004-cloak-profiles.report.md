# Report: 004 — Cloak profile integration and textsessions profile commands
Date: 2026-04-08T15:00:00Z
Status: DONE

## Changes

- `f832717` Focus session table on startup instead of filter input (contains config.py, app.py, cli.py changes)
- `ce7d50e` Add cloak + ai-proxy profile integration (profiles.py, tests/test_profiles.py)

### Files changed

- **`src/textsessions/profiles.py`** (new): Detection helpers — `cloak_available()`, `cloak_profile_dir()`, `list_cloak_profiles()`, `cloak_version()`, `aiproxy_available()`, `aiproxy_running()`, `build_launch_env()`
- **`src/textsessions/config.py`**: Added `IntegrationsConfig` dataclass (`cloak: bool`, `aiproxy: bool`), wired into `Config`, `load()`, `save()`
- **`src/textsessions/tui/app.py`**: Imports `build_launch_env` + `cloak_available`; passes env to subprocess in `action_resume_session` and `action_new_session`; adds dim cloak hint in `SessionDetail.render()` for non-default profiles when cloak not installed
- **`src/textsessions/cli.py`**: Added `textsessions profile` subcommand group with `status`, `list`, `setup`, `check` subcommands
- **`tests/test_profiles.py`** (new): 12 tests covering all helpers and env-building

## Test results

- textsessions: 77 tests passed, 0 failed

## Notes for next prompt

- `build_launch_env` is in `profiles.py` (not `app.py`) so tests don't require textual; app.py imports it
- The `default` profile never sets `CLAUDE_CONFIG_DIR` by design
- `textsessions profile setup <name>` prints the command to run manually — does NOT shell out to `cloak create` (requires interactive OAuth)
- `aiproxy_running()` uses 100ms socket timeout as specified
- Tests patch `os.environ` to `CLEAN_ENV` to avoid interference from the real environment where `CLAUDE_CONFIG_DIR` may already be set
