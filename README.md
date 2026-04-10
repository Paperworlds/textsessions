# textsessions

A terminal UI and CLI for managing [Claude Code](https://claude.ai/code) sessions across multiple Git repos.

If you work with Claude across many projects, sessions accumulate fast. textsessions gives you a searchable, filterable view of all of them — with resume, tagging, priority, and cleanup built in.

```
textsessions
```

![TUI showing session list with repo, profile, tags, priority, and last-active columns]

---

## Requirements

- Python 3.12+
- [fish shell](https://fishshell.com/) — required for `--resume` and new session launch
- Claude Code CLI (`claude`)

Optional integrations (auto-detected at runtime):
- [cloak](https://github.com/synth1s/cloak) — credential isolation per profile *(experimental — see note below)*
- [ai-proxy](https://github.com/pdonorio/claude-code-proxy) — local token proxy for usage tracking

---

## Install

```sh
pip install textsessions
```

Or from source:

```sh
git clone https://github.com/pdonorio/textsessions
cd textsessions
pip install -e .
```

Install fish completions:

```sh
cp completions/textsessions.fish ~/.config/fish/completions/
```

---

## Quick start

```sh
# 1. Detect repos from existing Claude session history
textsessions init

# 2. Build session indexes from .jsonl files
textsessions reindex

# 3. Launch the TUI
textsessions
```

---

## TUI

Launch with `textsessions` (or alias `ts`).

Sessions are grouped by repo and sorted by last-active. The right panel shows full detail for the selected session, including token proxy stats if ai-proxy is running.

### Keyboard shortcuts

| Key | Action |
|-----|--------|
| `Enter` | Resume session (suspends TUI, launches Claude, returns) |
| `n` | New session (profile, repo, optional name) |
| `/` | Filter by name, description, or slug |
| `a` | Toggle: current repo ↔ all repos |
| `t` | Tag / untag (comma-separated; prefix `-` to remove) |
| `p` | Set priority (H0 = urgent, 1–3, or clear) |
| `r` | Rename (sets a short display name + description) |
| `x` | Pin / unpin session |
| `y` | Toggle pinned sessions visibility |
| `d` | Archive (hidden but recoverable) |
| `D` | Hard delete (confirmation required) |
| `g` | Toggle ghosts & orphans only view |
| `s` | Sort by priority instead of last-active |
| `ctrl+r` | Reindex current repo |
| `?` | Help |
| `q` | Quit |

---

## CLI reference

### Sessions

```sh
# List sessions
textsessions sessions
textsessions sessions --repo mono --tag auth --limit 10

# Resume a session by name (fish tab-completion supported)
textsessions sessions --resume my-feature-work

# Filter to current folder's repo
textsessions sessions --current-folder
```

### AI search

```sh
textsessions search "add client to privatelink"
textsessions search "auth refactor" --repo mono --limit 5 --json
```

Sends session metadata to Claude and returns ranked matches. Requires a Claude command to be configured as `ui.ai_search_profile` (default: `claude`).

### Cleanup

```sh
# Dry-run report of ghosts (dead repos) and orphans (throwaway hex-named sessions)
textsessions scan-ghosts

# Archive all (reversible — hides from normal view)
textsessions scan-ghosts --archive

# Bulk archive for one repo without confirmation
textsessions scan-ghosts --repo mono --discard

# Mark a hex-named session as "keep" (exclude from future orphan detection)
textsessions scan-ghosts --keep abc123 --repo mono

# Hard delete (irreversible)
textsessions scan-ghosts --delete --yes
```

### Rename hex-named sessions

Claude auto-names new sessions with a hex ID. When you use `/rename` inside a session, textsessions can pick that up:

```sh
textsessions index auto-rename --dry-run   # preview
textsessions index auto-rename             # apply to all repos
```

Only renames sessions that have a `/rename` entry in their `.jsonl` — never guesses.

### Reindex

```sh
textsessions reindex             # all configured repos
textsessions reindex --repo mono # one repo
```

Rebuilds YAML indexes from `.jsonl` files. Preserves tags, priority, pinned state, and custom names.

### Export

```sh
textsessions tree                          # YAML tree of all repos + sessions
textsessions tree --format json -o out.json
textsessions tree --repo mono --include-archived
```

### Proxy stats

```sh
textsessions proxy    # token usage + cost for today, by model
```

Reads from ai-proxy's cache. Shows nothing if ai-proxy is not running.

### Config

```sh
textsessions config   # show current config path and repo list
```

---

## Configuration

`~/.config/textsessions/config.toml`

```toml
[[repos]]
path = "/Users/you/projects/myrepo"
label = "myrepo"
profile = "default"          # maps to a cloak profile (optional)

[[repos]]
path = "/Users/you/projects"
label = "personal"
profile = "personal"
recursive = true             # scan all git repos one level deep

[ui]
startup_repo = "current"     # "current" = auto-filter TUI to cwd repo | "all" = show everything
claude_cmd = "claude"        # command to launch Claude; {profile} is substituted if present
                             # e.g. "claude-{profile}" dispatches to fish functions like claude-work
ai_search_profile = "claude" # command used for `textsessions search`

[integrations]
cloak = true    # use cloak for credential isolation if installed (see below)
aiproxy = true  # inject ANTHROPIC_BASE_URL if ai-proxy is running on :7474

[proxy]
cache_dir = "~/.cache/ai-proxy"
```

### Profiles and the `claude_cmd` template

Each repo has a `profile`. When launching or resuming a session, textsessions resolves the command to run via `claude_cmd` with `{profile}` substituted:

```toml
claude_cmd = "claude-{profile}"
# mono (profile=work)    → runs: claude-work
# blog (profile=default) → runs: claude-default
```

This lets you define fish functions (`claude-work`, `claude-personal`, etc.) that set environment or flags before calling `claude`. Useful for routing to different API keys or base URLs without cloak.

---

## Integrations

### ai-proxy

If [ai-proxy](https://github.com/pdonorio/claude-code-proxy) is running on `localhost:7474`, textsessions automatically sets `ANTHROPIC_BASE_URL` before launching Claude. Token usage and cost appear in the TUI detail panel and `textsessions proxy`.

### cloak *(experimental)*

[cloak](https://github.com/synth1s/cloak) isolates Claude accounts by storing each profile's config in a separate directory. textsessions injects `CLAUDE_CONFIG_DIR=~/.cloak/profiles/<profile>` when launching sessions.

> **Note:** cloak integration has not been thoroughly tested. The setup flow is documented in [`docs/cloak-setup.md`](docs/cloak-setup.md) but should be considered experimental. Feedback welcome.

```sh
textsessions profile status   # check cloak and ai-proxy state
textsessions profile list     # profiles → repos mapping
textsessions profile check    # verify all configured profiles have cloak dirs
textsessions profile setup work
```

Set `cloak = false` under `[integrations]` to disable entirely.

---

## How it works

Claude Code stores every conversation as a `.jsonl` file under `~/.claude*/projects/<repo-key>/`. textsessions reads these files and builds a lightweight YAML index per repo at `~/.local/state/claude-sessions/<repo-key>.yaml`.

The index stores: session name, profile, last-active timestamp, slug, tags, priority, pinned state, and description. It is rebuilt with `textsessions reindex` and preserves all user-set metadata across rebuilds.

---

## Part of PaperWorlds

textsessions is the first open-source release from [PaperWorlds](https://github.com/pdonorio/paperworlds) — a personal project building tools and games around AI agents and text interfaces.

---

## License

MIT
