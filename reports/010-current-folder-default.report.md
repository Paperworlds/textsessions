# Report: 010 — TUI: default to current folder view, A to show all
Date: 2026-04-09T00:00:00Z
Status: DONE

## Changes
- 74d6785 prompt 010: TUI default to current folder, A to show all (textsessions)

## Test results
- textsessions: 91 tests passed

## Notes for next prompt
- `_repo_filter` is now separate from `_filter_query` — text search and repo filter compose cleanly
- `_cwd_repo_label` is set once on mount; "A" toggles between it and "" (all repos)
- If the user is outside any configured repo, "A" is a no-op (cwd_repo_label stays "")
- Scope label uses `[dim]` markup via Textual's Rich renderer
