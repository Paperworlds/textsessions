# Report: 014 — TUI: y key toggles pinned sessions visibility
Date: 2026-04-09T00:00:00Z
Status: DONE

## Changes
- 38f85e1 prompt 014: y key toggles pinned sessions visibility (textsessions)

## Changes made
- `src/textsessions/tui/app.py`:
  - Added `_show_pinned: reactive[bool] = reactive(True)` reactive
  - Added `Binding("y", "toggle_pins", "Pins")` to BINDINGS
  - Added `if not self._show_pinned:` filter in `_apply_filter`
  - Refactored `watch__repo_filter` to delegate to `_update_scope_label()`
  - Added `watch__show_pinned` watcher calling `_update_scope_label()`
  - Added `_update_scope_label()` method that appends `[dim red]pins hidden[/dim red]` when pins are hidden
  - Added `action_toggle_pins()` method with notify toast
- `src/textsessions/tui/modals.py`:
  - Added `("y", "Toggle pinned visibility")` to `HelpModal.HELP_ROWS`

## Test results
- Import check: PASS
- No unit tests required per spec

## Notes for next prompt
- `_show_pinned` is not persisted across sessions (resets to True on restart) — could be added to config if desired
