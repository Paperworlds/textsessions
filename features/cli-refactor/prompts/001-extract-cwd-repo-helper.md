---
id: "001"
title: "Extract CWD→repo detection helper"
repo: "textsessions"
model: "sonnet"
depends_on: []
budget_usd: 1.50
---

# 001 — Extract CWD→repo detection helper

## Goal

The logic that resolves the current working directory to the best-matching
`RepoConfig` is duplicated verbatim in two CLI commands. Extract it into a
shared private helper so there's one place to maintain.

## Where the duplication lives

`src/textsessions/cli.py`:

- `new_cmd` (the `new` command): lines ~125-143 — resolves CWD to a repo when
  `--repo` is not passed.
- `sessions_cmd` (the `sessions` command): lines ~353-372 — resolves CWD to a
  repo when `--current-folder` is passed.

Both blocks do exactly the same thing:
1. Iterate `config.repos`
2. Try `cwd.relative_to(r.path)` — skip on `ValueError`
3. Track the deepest match by `len(r.path.parts)`
4. Warn if the matched repo is a parent and `cwd/.git` exists
5. Error and exit if nothing matched

## What to do

1. Extract the shared logic into a module-level helper:

   ```python
   def _resolve_repo_from_cwd(config) -> RepoConfig:
   ```

2. Replace both call sites with `repo = _resolve_repo_from_cwd(config)`.

3. The warning and error messages must stay exactly as they are — no text changes.

4. Add a regression test in `tests/` that covers:
   - exact match (cwd == repo.path)
   - child directory match (cwd is under repo.path)
   - no match → SystemExit

## Verification

- `pytest` passes
- `ts new` (without `--repo`) still works from inside a configured repo dir
- `ts sessions --current-folder` still works
