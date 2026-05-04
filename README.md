# textsessions

A terminal UI and CLI for managing [Claude Code](https://claude.ai/code) sessions across multiple Git repos.

If you work with Claude across many projects, sessions accumulate fast. textsessions gives you a searchable, filterable view of all of them — with resume, tagging, priority, and cleanup built in.

```
textsessions view
```

![TUI showing session list with repo, profile, tags, priority, and last-active columns]

> **Claude Code only.** textsessions is built and tested exclusively with [Claude Code](https://claude.ai/code). It reads the `.jsonl` session files that Claude Code writes to disk and is not compatible with other AI coding assistants.

---

## Requirements

- Python 3.12+
- [fish shell](https://fishshell.com/) — required for `--resume` and new session launch
- Claude Code CLI (`claude`)

Optional integrations (auto-detected at runtime):
- [textaccounts](#textaccounts) — profile isolation (separate optional package)
- [textproxy](https://github.com/paperworlds/textproxy) — local token proxy for tracking context consumption

---

## Install

```sh
pip install textsessions
```

With multi-account support ([textaccounts](https://github.com/paperworlds/textaccounts)):

```sh
pip install textsessions[accounts]
```

Or from source:

```sh
git clone https://github.com/paperworlds/textsessions
cd textsessions
pip install -e ".[accounts]"
```

---

## Quick start

```sh
# 1. Detect repos from existing Claude session history
textsessions init

# 2. Build session indexes from .jsonl files
textsessions reindex

# 3. Launch the TUI
textsessions view
```

---

## TUI

Launch with `textsessions view` (or alias `ts`).

Sessions are grouped by repo and sorted by last-active. The right panel shows full detail for the selected session, including token proxy stats if textproxy is running.

When resuming a session inside tmux, the tmux window is automatically renamed to the session name for easy identification across panes.

### Keyboard shortcuts

| Key | Action |
|-----|--------|
| `Enter` | Resume session (suspends TUI, launches Claude, returns; renames tmux window) |
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
| `c` | Open repo config view |
| `?` | Help |
| `q` | Quit |

---

## CLI reference

### View

```sh
textsessions view             # launch the TUI
textsessions view --config    # open repo config view
```

### Add repos

```sh
textsessions add /path/to/repo                          # auto-label from dirname
textsessions add /path/to/repo --label myrepo           # custom label
textsessions add /path/to/repo --profile work           # assign a profile
textsessions add /path/to/projects --recursive          # scan one level deep
```

### Sessions

```sh
# List sessions
textsessions sessions
textsessions sessions --repo mono --tag auth --limit 10

# Resume a session by name (tab-completion supported)
textsessions sessions --resume my-feature-work

# Filter to current folder's repo
textsessions sessions --current-folder

# Shallow-clone lineage filters (require textaccounts)
textsessions sessions --shallow-only            # only sessions on shallow profiles
textsessions sessions --no-shallow              # hide them
textsessions sessions --parent personal         # shallow profiles cloned from `personal`
textsessions sessions --owner pp:run-7          # match an exact owner id (hint or lineage)

# Persona/label filters (require a hint file — see "Specs" below)
textsessions sessions --persona agentic-pivot
textsessions sessions --label pivot
```

The table shows: **Name**, **Info** (description if set, otherwise the auto-generated slug), Repo, Profile, Tags, Priority, Last Active.

When any visible session runs on a shallow-clone profile, a **Lineage** column appears with chips like `[shallow ← personal, ephemeral, owner=pp:run-7]`. When any session has a hint file, a **Persona** column appears with chips like `[persona=agentic-pivot, #pivot #private]`. Both chips are also rendered in the TUI row and detail panel.

### Rename and tag

```sh
# Rename a session (tab-completes session names)
textsessions rename my-feature-work "Better title for this session"

# Add tags
textsessions tag my-feature-work auth,api

# Remove tags (prefix with -)
textsessions tag my-feature-work -auth

# Add and remove in one shot
textsessions tag my-feature-work api,-old,keep
```

### AI search

```sh
textsessions search "add client to privatelink"
textsessions search "auth refactor" --repo mono --limit 5 --json
textsessions search "auth refactor" --profile work    # use a textaccounts profile for the search
```

Sends session metadata to Claude and returns ranked matches. With `--profile`, the underlying `claude -p` call runs under that textaccounts profile (validated up front).

### Jump

Resume the latest (or lead) session in a repo with one keystroke. From inside a configured repo, no argument is needed:

```sh
textsessions jump                       # resume the latest interactive session in the CWD repo
textsessions jump textsessions          # explicit repo label
textsessions jump textsessions --lead   # pinned (or `lead`-labelled) session instead of latest
textsessions jump --dry-run             # print what would resume, don't exec
```

Skips automated runners (pp workers, CI) and hex-named throwaway sessions. With `--lead`, matches sessions you've pinned in the TUI (`p` key) **or** sessions whose textsessions-hints file carries `labels: [lead]`.

### Shallow profiles

`ts shallow new` creates a [shallow-clone](https://github.com/paperworlds/textaccounts/blob/main/docs/specs/shallow-clone.md) profile by delegating to `textaccounts create`. Useful for parallel agent runs that need their own auth without copying the whole config:

```sh
textsessions shallow new scratch-1 --from personal                       # plain shallow
textsessions shallow new pp-run-7 --from personal --owner pp:run-7       # implies --ephemeral
textsessions shallow new tmp --from work --ephemeral                     # GC-eligible
```

Validates that textaccounts is installed and configured, the parent profile exists, and the new name is free before invoking the CLI. Sessions launched on these profiles automatically get the lineage chip described under [Sessions](#sessions).

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

Reads from textproxy's cache. Shows nothing if textproxy is not running.

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
profile = "default"          # maps to a textaccounts profile (optional)

[[repos]]
path = "/Users/you/projects"
label = "personal"
profile = "personal"
recursive = true             # scan all git repos one level deep

[ui]
startup_repo = "current"     # "current" = auto-filter TUI to cwd repo | "all" = show everything

[integrations]
textaccounts = true  # use textaccounts for profile isolation if configured (see below)
textproxy = true     # inject ANTHROPIC_BASE_URL if textproxy is running on :7474

[proxy]
cache_dir = "~/.cache/textproxy"
```

### Profiles

Each repo has a `profile` (a textaccounts profile name, or `default` for no isolation). Profile switching is delegated to textaccounts via its public `textaccounts.api` surface — textsessions injects `CLAUDE_CONFIG_DIR` into the launched `claude` process based on the repo's profile. No custom shell wrappers required.

---

## Integrations

### textproxy

[textproxy](https://github.com/paperworlds/textproxy) is a companion paperworlds project — a lightweight local MITM proxy that captures token consumption stats from Claude Code API traffic. It gives subscription users (Claude Team, Claude.ai) visibility into how much context window each session is actually consuming, without modifying Claude Code itself.

If textproxy is running on `localhost:7474`, textsessions automatically sets `ANTHROPIC_BASE_URL` before launching Claude. Token usage and cost appear in the TUI detail panel and `textsessions proxy`.

### textaccounts

[textaccounts](https://github.com/paperworlds/textaccounts) is an optional profile manager that isolates Claude accounts by pointing `CLAUDE_CONFIG_DIR` at separate config directories — keeping sessions, memory, and auth separate per profile.

Install with `pip install textsessions[accounts]` to enable. When configured, textsessions automatically injects `CLAUDE_CONFIG_DIR` before launching or resuming any session whose repo `profile` matches a registered profile name. Without textaccounts, you can still use custom commands (see Custom Commands section above) or a single default account.

#### Setup flow

**1. Install shell integration:**

```sh
textaccounts install        # writes fish function + completions to ~/.config/fish/
```

**2. Register your existing Claude config dirs** — nothing moves, just registers the paths:

```sh
textaccounts adopt work ~/.claude-work
textaccounts adopt personal ~/.claude-personal
```

**3. Switch profiles:**

```sh
textaccounts switch work       # sets CLAUDE_CONFIG_DIR=~/.claude-work in your shell
textaccounts switch personal   # sets CLAUDE_CONFIG_DIR=~/.claude-personal
textaccounts switch default    # unsets CLAUDE_CONFIG_DIR (back to ~/.claude)
```

**4. Wire repos to profiles** in your config:

```toml
[[repos]]
path = "/Users/you/work/myrepo"
label = "myrepo"
profile = "work"        # textsessions will inject CLAUDE_CONFIG_DIR for this profile
```

#### All commands

```sh
textaccounts list                        # show all profiles with path, email, session count, size
textaccounts status                      # active profile, env var sync check, session count
textaccounts adopt <name> <path>         # register an existing dir
textaccounts create <name>               # snapshot current config dir into ~/.textaccounts/profiles/
textaccounts create <name> --worker \
  --from <parent>                        # minimal copy: .claude.json + settings.json only
textaccounts switch <name>               # switch profile (sets CLAUDE_CONFIG_DIR)
textaccounts show <name>                 # print the shell command without executing
textaccounts rename <old> <new>          # rename a profile
textaccounts alias <profile> <alias>     # add a short alias
textaccounts view                        # interactive profile view
textaccounts install                     # install shell integration
```

Set `textaccounts = false` or `textproxy = false` under `[integrations]` to disable either integration.

---

## How it works

Claude Code stores every conversation as a `.jsonl` file under `~/.claude*/projects/<repo-key>/`. textsessions reads these files and builds a lightweight YAML index per repo at `~/.local/state/claude-sessions/<repo-key>.yaml`.

The index stores: session name, profile, last-active timestamp, slug, tags, priority, pinned state, and description. It is rebuilt with `textsessions reindex` and preserves all user-set metadata across rebuilds.

---

## Ask Claude about this tool

If you use Claude Code, you can paste this prompt to get a quick orientation:

```
Read the file at docs/features.yaml in this repo and tell me:
1. What textsessions does and who it's for
2. Which features are most relevant to my workflow (ask me 2-3 questions first)
3. The first 3 commands I should run to get started
```

Or for a deeper dive:

```
Read docs/features.yaml and give me a tour of textsessions.
For each feature, tell me when I'd use it and show me the exact command.
Start with the ones that solve the most common pain points for heavy Claude Code users.
```

---

## Specs

textsessions consumes specs published by other paperworlds tools, and owns one of its own:

- **`textaccounts-api` v0.2.0** (consumer) — read-only public Python API for profile metadata, including shallow-clone lineage. textsessions imports only from `textaccounts.api`. See [docs/SPECS.yaml](docs/SPECS.yaml).
- **`textsessions-hints` v0.1.0** (owner, draft producers) — file-based contract for annotating sessions at launch time with `{persona, owner, labels}`. textsessions reads `~/.cache/textsessions/hints/<session-uuid>.yaml`; producers like [textprompts](https://github.com/paperworlds/textprompts) write them. See [docs/specs/textsessions-hints.md](docs/specs/textsessions-hints.md).

---

## Roadmap

- [x] Publish to PyPI
- [x] Upgrade to Python 3.13
- [x] Surface shallow-clone lineage in CLI + TUI (`--shallow-only`, `--parent`, `--owner`, lineage chip)
- [x] `ts shallow new` — create shallow-clone profiles by delegating to `textaccounts create`
- [x] Persona-aware sessions — consume `textsessions-hints` (persona column, `--persona`/`--label` filters; producer side in textprompts is the open task)
- [x] `ts jump <repo>` — drop into the latest (or lead) session for a repo with one keystroke
- [ ] Bash/zsh shell support (currently fish only)
- [ ] `textsessions doctor` — validate config, check for stale paths
- [ ] Session export to markdown
- [ ] Refactor config screen from subprocess to pushed Screen (removes brief flash on `c` key, enables Enter-to-filter)
- [ ] Polish rename flow — reindex now auto-renames hex sessions from `/rename`, but edge cases remain: TUI `r` key doesn't update the tmux window name, stale tab-completion names after rename, and `auto-rename --dry-run` output could be clearer

> [!NOTE]
> **Part of Paperworlds**
>
> textsessions is part of [Paperworlds](https://github.com/paperworlds) — an open org building tools and games around AI agents and text interfaces.

## License

MIT
