# Report: 006 — Config option: start TUI filtered to current repo or show all
Date: 2026-04-08T00:00:00Z
Status: DONE

## Changes
- 413e25e Add startup_repo config option to pre-filter TUI on launch (textsessions)

## Test results
- textsessions: 83 tests passed, 0 failed

## Notes for next prompt
- `UiConfig` dataclass is now in `config.py`; future UI options can be added there
- `_repo_for_cwd` is a module-level function in `tui/app.py`, exported and testable
- Filter is applied before `_populate_table` in `on_mount`; the Input widget value is also set so the filter box shows the pre-applied query
