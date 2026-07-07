---
id: "003"
title: "CLI tag/rename commands: use mutate_index"
repo: "textsessions"
model: "sonnet"
depends_on: []
budget_usd: 1.00
---

# 003 — CLI tag/rename commands: use mutate_index

## Goal

`rename_cmd` and `tag_cmd` in `src/textsessions/cli.py` manually do the
load-index → mutate → save-index → write-legacy-tsv dance. The TUI uses
`mutate_index(key, sid, fn)` from `indexer.py` for all index mutations.
Make the CLI commands consistent with the TUI.

## Current code

`rename_cmd` (~lines 448-460):
```python
rk = _repo_key(s.repo_path)
index = load_index(rk)
index = do_rename(index, s.id, title, repo_key=rk)
save_index(rk, index)
write_legacy_tsv(rk, index)
```

`tag_cmd` (~lines 466-484):
```python
rk = _repo_key(s.repo_path)
index = load_index(rk)
...
if to_add:
    index = do_tag(index, s.id, ",".join(to_add))
if to_remove:
    index = do_untag(index, s.id, ",".join(to_remove))
save_index(rk, index)
write_legacy_tsv(rk, index)
```

## What to do

Replace both with `mutate_index(key, sid, fn)` calls, matching the TUI pattern
in `tui/actions.py` (see `action_rename_session` and `action_tag_session`).

`mutate_index` signature (from `indexer.py`):
```python
def mutate_index(key: str, session_id: str, fn) -> None:
    """Load index, call fn(index, sid), save index and write legacy TSV."""
```

After the change:

`rename_cmd`:
```python
rk = _repo_key(s.repo_path)
mutate_index(rk, s.id, lambda index, sid: do_rename(index, sid, title, repo_key=rk))
```

`tag_cmd`:
```python
def apply(index, sid):
    if to_add:
        do_tag(index, sid, ",".join(to_add))
    if to_remove:
        do_untag(index, sid, ",".join(to_remove))
mutate_index(rk, s.id, apply)
```

Update imports accordingly (add `mutate_index`, remove manual
`load_index`/`save_index`/`write_legacy_tsv` if no longer needed in these commands).

## Constraints

- No behaviour change
- Check whether `write_legacy_tsv` is still called separately; if `mutate_index`
  already calls it internally, don't call it twice

## Verification

- `pytest` passes
- `ts rename <name> new title` still works
- `ts tag <name> auth,-old` still works
