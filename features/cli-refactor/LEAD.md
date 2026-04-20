# cli-refactor — Feature Context

Feature of: textsessions

Three targeted refactors in `src/textsessions/cli.py` to reduce duplication and
improve maintainability. Each prompt is self-contained and independent.

## Feature scope

- Extract duplicated CWD→repo detection into a shared helper
- Break up the oversized `scan-ghosts` command into subfunctions
- Make CLI tag/rename commands use `mutate_index` instead of manual load/save

## What exists

- `src/textsessions/cli.py` (~1400 lines): main CLI entrypoint
- `src/textsessions/indexer.py`: `mutate_index(key, sid, fn)` already exists and
  is used by the TUI (`tui/actions.py`) for all index mutations
- The TUI (`tui/actions.py`) uses `mutate_index` for tag, rename, pin, priority
- `tests/` — regression tests required for any behaviour change

## Constraints

- Python 3.14, no new dependencies
- All tests must pass: `pytest`
- Commit after each logical unit of work (`git -c commit.gpgsign=false commit`)
- No docstrings, type annotations, or comments added to untouched code
- No behaviour changes — pure structural refactors only
