# Testing — textsessions + textaccounts

## Manual QA checklist

Walk through these before a public release. Each section is a user story — run the commands, verify the expected outcome.

### First-time setup

- [ ] `textsessions init` — scans for Claude session dirs, prompts for repo labels and profiles
- [ ] `textsessions config` — prints the generated `~/.config/textsessions/config.toml`
- [ ] `textsessions reindex` — builds YAML indexes from .jsonl session files

### Browse and filter

- [ ] `textsessions` — TUI launches, shows session table
- [ ] `/` — filter input focuses, typing narrows the list
- [ ] `#tag` in filter — filters to sessions with that tag
- [ ] `a` — toggles between current-repo and all-repos view
- [ ] `s` — toggles sort (priority vs last-active)
- [ ] `escape` — clears filter
- [ ] Arrow keys / scroll — navigate sessions, right panel updates

### Session lifecycle

- [ ] `enter` — resumes selected session (Claude opens with `--resume`)
- [ ] `n` — new session modal opens, can pick repo and profile
- [ ] `r` — rename modal, new title persists after reindex
- [ ] `t` — tag modal, add/remove tags (prefix `-` to remove)
- [ ] `p` — priority modal (H0/1/2/3 or clear)
- [ ] `x` — pin/unpin a session
- [ ] `y` — toggle pinned-only view
- [ ] `d` — archive modal (archive or hard delete)
- [ ] `D` — hard delete with inline confirmation

### Ghost/orphan cleanup

- [ ] `g` — toggle ghost-only view in TUI
- [ ] `textsessions scan-ghosts` — lists detected ghosts and orphans
- [ ] `textsessions scan-ghosts --archive` — tags them as archived

### CLI operations

- [ ] `textsessions sessions` — lists sessions in terminal
- [ ] `textsessions sessions --filter "keyword"` — filters output
- [ ] `textsessions sessions --resume "name"` — resumes by name
- [ ] `textsessions rename "name" "new title"` — renames from CLI
- [ ] `textsessions tag "name" "bug,wip"` — adds tags from CLI
- [ ] `textsessions tree --format yaml` — exports session tree
- [ ] `textsessions search "what did I work on yesterday"` — AI search returns relevant sessions

### Profile integration (tier 1 — with textaccounts)

Requires `pip install textsessions[accounts]` and textaccounts configured.

- [ ] `textaccounts status` — shows active profile
- [ ] `textaccounts list` — shows all profiles
- [ ] Resume a session from a non-default profile — verify `CLAUDE_CONFIG_DIR` is set in the subprocess
- [ ] `n` (new session) — profile from repo config is applied
- [ ] TUI shows profile column with correct values per session

### Profile integration (tier 2 — custom commands, no textaccounts)

Set `claude_cmd = "claude-{profile}"` in config.toml. No textaccounts installed.

- [ ] Resume a session — verify the expanded command runs (e.g. `claude-work --resume ...`)
- [ ] TUI loads without errors, no textaccounts hints shown

### Profile integration (tier 3 — single account)

Plain install, default config.

- [ ] Resume a session — plain `claude --resume ...` runs
- [ ] TUI loads without errors

### Proxy integration (optional)

- [ ] With ai-proxy running on :7474 — `textsessions proxy` shows token stats
- [ ] Resume a session — `ANTHROPIC_BASE_URL` is set in subprocess env
- [ ] Without ai-proxy — no errors, proxy column hidden

### Reindex and data integrity

- [ ] `ctrl+r` in TUI — reindexes, session list refreshes
- [ ] `textsessions reindex --repo "label"` — reindexes specific repo
- [ ] After rename/tag/priority changes, reindex does NOT lose the changes

### Edge cases

- [ ] TUI with zero sessions — shows empty state, no crash
- [ ] TUI with a repo whose path no longer exists — shows ghost indicator
- [ ] Filter with no matches — empty table, no crash
- [ ] Resume a session whose .jsonl was deleted — graceful error

---

## Automated tests

### textaccounts (standalone)

```sh
cd textaccounts
uv run pytest -x -q          # 52 tests
```

### textsessions

```sh
cd textsessions
uv run pytest -x -q          # 109 tests
```

### textsessions + textaccounts (integration)

```sh
cd textsessions
uv pip install -e ../textaccounts
uv run pytest -x -q          # same 109, but textaccounts.api imports are live
```

---

## Release flow

Order matters — textaccounts must be pushed first since textsessions depends on it via git URL.

### 1. textaccounts

```sh
cd textaccounts
uv run pytest -x -q
git add -A && git commit -m "feat: description"
git tag v0.X.0
git push && git push --tags
gh run watch
```

### 2. textsessions — pin to new tag

Update `pyproject.toml` to pin the textaccounts dependency:

```toml
[project.optional-dependencies]
accounts = [
    "textaccounts @ git+https://github.com/Paperworlds/textaccounts.git@v0.X.0",
]
```

```sh
cd textsessions
uv run pytest -x -q
git add -A && git commit -m "feat: description"
git push
gh run watch
```

### 3. Fresh install smoke test

```sh
# standalone
uv tool install textaccounts
textaccounts list && textaccounts status

# with accounts
uv tool install "textsessions[accounts]"
textsessions

# without accounts
uv tool install textsessions
textsessions
```

---

## Three tiers of profile support

| Tier | Install | How profiles work |
|------|---------|-------------------|
| 1 | `textsessions[accounts]` | textaccounts API sets `CLAUDE_CONFIG_DIR` automatically |
| 2 | `textsessions` + custom commands | `claude_cmd = "claude-{profile}"` in config.toml |
| 3 | `textsessions` | Single account, plain `claude` |

---

## Local dev workflow

```sh
cd textsessions
uv pip install -e ../textaccounts    # editable, changes reflect immediately
uv run pytest -x -q
```
