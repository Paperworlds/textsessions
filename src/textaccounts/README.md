# textaccounts

Manage multiple Claude Code accounts by treating full config directories as profiles. A native Python replacement for `cloak` that understands the real structure of `~/.claude/`.

## Motivation

[cloak](https://github.com/nickvdyck/cloak) manages Claude Code profiles by swapping two files — your auth token and settings. `textaccounts` treats each profile as a **full config directory**, because that's what Claude Code actually uses.

When you switch profiles with cloak, your session history, project memory (`CLAUDE.md` files), and agent state are shared across all profiles (or lost entirely). `textaccounts` keeps everything isolated by pointing `CLAUDE_CONFIG_DIR` at a complete, independent directory per profile.

## cloak vs textaccounts

| | cloak | textaccounts |
|---|---|---|
| What's a profile? | 2 files (auth + settings) | Full config dir |
| Profile dir | hardcoded `~/.cloak/profiles/` | configurable, default `~/.textaccounts/profiles/` |
| Sessions | lost per switch | preserved per profile |
| Memory/CLAUDE.md | shared fallthrough | isolated per profile |
| Install | npm | pip/pipx (same as textsessions) |
| Adopt existing dirs | no | yes (`adopt` command) |

## Design decisions

**Full dirs, not 2 files** — Claude Code stores sessions, project memory, agent state, and OAuth tokens in a single directory tree. Swapping only 2 files leaves everything else shared. Pointing `CLAUDE_CONFIG_DIR` at a complete directory gives true isolation.

**YAML, not TOML** — The profile registry has dynamic keys (profile names) and nested optional fields. YAML handles this more naturally than TOML, and it differentiates the registry format from `textsessions`' own TOML config.

**`adopt` over `create`** — If you already have `~/.claude-work/` and `~/.claude-personal/`, you shouldn't have to copy anything. `adopt` registers existing directories as profiles with no data movement.

**Fish native** — `switch` prints a `set -x CLAUDE_CONFIG_DIR ...` line for `eval`. The `ta` wrapper handles this transparently. No bash eval hacks; fish functions set the parent shell environment correctly.

## Installation

```sh
pipx install textsessions   # textaccounts ships as part of textsessions
# or install standalone once published:
pipx install textaccounts
```

## CLI reference

```
textaccounts adopt <name> <path>                     # register existing dir as profile
textaccounts create <name>                           # snapshot current config dir
textaccounts create <name> --worker --from <parent>  # worker profile (auth-only copy)
textaccounts list                                    # show all profiles
textaccounts switch <name>                           # print fish env line, update registry
textaccounts status                                  # active profile info
```

### Fish shell integration

Add to `~/.config/fish/config.fish`:

```fish
function ta --description "textaccounts shorthand"
    if test (count $argv) -ge 1; and test "$argv[1]" = "switch"
        eval (textaccounts switch $argv[2..-1])
    else
        textaccounts $argv
    end
end
```

Then use `ta switch work` instead of `eval (textaccounts switch work)`.

## Config schema

Config file: `~/.textaccounts/profiles.yaml`

```yaml
version: 1
active: work

profiles:
  work:
    path: /Users/you/.claude-work
    email: you@example.com
    adopted: 2026-04-12T10:00:00Z
    worker: false
  personal:
    path: /Users/you/.claude-personal
    email: y***@personal.dev
    adopted: 2026-04-12T10:00:00Z
    worker: false
  work-worker:
    path: /Users/you/.textaccounts/profiles/work-worker
    email: you@example.com
    worker: true
    parent: work

defaults:
  profiles_dir: ~/.textaccounts/profiles
```

### Profile fields

| Field | Type | Required | Description |
|---|---|---|---|
| `path` | absolute path | yes | Full Claude config directory |
| `email` | string | no | Cached from `.claude.json` (masked) |
| `adopted` | ISO timestamp | no | When this profile was registered |
| `worker` | bool | no | Auth-only copy for parallel work |
| `parent` | string | if worker | Source profile name |

## Migration guide

If you already have Claude config directories (e.g. `~/.claude-work`, `~/.claude-personal`):

```sh
# Register existing directories — no data is copied or moved
textaccounts adopt work ~/.claude-work
textaccounts adopt personal ~/.claude-personal

# Verify
textaccounts list

# Switch to a profile
ta switch work
```

Your session history, project memory, and auth tokens remain exactly where they are. `textaccounts` only writes a YAML entry pointing at each directory.
