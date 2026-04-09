# Report: 013 — TUI: ? key shows help modal with all keybindings
Date: 2026-04-09T00:00:00Z
Status: DONE

## Changes
- 6ffb34a prompt 013: ? key shows help modal with all keybindings (textsessions)

## Test results
- textsessions: 100 tests passed

## Notes for next prompt
- HelpModal is in `tui/modals.py`, exported at the top-level import in `app.py`
- HELP_ROWS is manually maintained — keep in sync if new bindings are added
