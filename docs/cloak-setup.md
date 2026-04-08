# Cloak Setup Guide

[cloak](https://github.com/synth1s/cloak) manages multiple Claude Code
identities by isolating each profile in its own config directory. `textsessions`
uses it to launch sessions under the right account without manual login switching.

## Prerequisites

- Node.js 18+ (you have v20 — good)
- Multiple Claude accounts (work, personal, etc.)
- `textsessions` configured with repos mapped to profiles

> **Fish shell note:** cloak's `claude -a <profile>` shell integration is
> Bash/Zsh only. You don't need it — `textsessions` handles the
> `CLAUDE_CONFIG_DIR` injection itself when launching sessions.

---

## Step 1 — Install cloak

```sh
npm install -g @synth1s/cloak
cloak --version  # verify
```

---

## Step 2 — Save your current session as a profile

Your current active Claude account (whichever is logged in right now) gets
saved first. Pick the name that matches what's in your `textsessions` config
— check with:

```sh
cat ~/.config/textsessions/config.toml | grep profile
```

You likely see: `personal`, `work`, `default`.

Save the currently logged-in account:

```sh
cloak create work     # or personal — whichever is active now
```

This snapshots `~/.claude/` into `~/.cloak/profiles/work/`.

---

## Step 3 — Create the second profile

Log out of Claude Code, sign into the other account, then:

```sh
cloak create personal
```

Repeat for any additional profiles.

---

## Step 3b — Create worker profiles

For each account, create a corresponding `<account>-worker` profile. Worker
profiles share the same credentials but start with **zero memory** — no
`CLAUDE.md`, no auto-loaded context. They are used by headless tools like
`pp` (paperagents), CI runs, and any other automation that should not
accumulate personal memory or be influenced by interactive session history.

With your **work** account active:

```sh
cloak create work-worker
# then wipe memory — same creds, clean slate:
rm -f ~/.cloak/profiles/work-worker/CLAUDE.md
```

With your **personal** account active:

```sh
cloak create personal-worker
rm -f ~/.cloak/profiles/personal-worker/CLAUDE.md
```

> `pp` runs use `--bare` by default (disables auto-memory at the Claude level
> too), but having an isolated worker profile adds a second layer of isolation
> and lets other tools (not just pp) opt into a clean environment without
> touching your real profile.

---

## Step 4 — Verify

```sh
cloak list
# should show: work, personal (or whichever you created)

ls ~/.cloak/profiles/
# work/  personal/
```

---

## Step 5 — Check textsessions sees it

```sh
textsessions profile status
textsessions profile list
textsessions profile check   # flags any repos whose profile has no cloak dir
```

If a profile is missing, go back to Step 3 for that account.

---

## How textsessions uses cloak

When you resume or create a session, textsessions sets:

```
CLAUDE_CONFIG_DIR=~/.cloak/profiles/<profile>
```

in the subprocess environment before launching `claude`. No shell integration
needed. The `default` profile always uses the system Claude config (no env
override).

You can disable cloak entirely (fall back to single-account mode) in your
config:

```toml
[integrations]
cloak = false
```

---

## Troubleshooting

**Sessions mixing between accounts after setup:**
Run `textsessions profile check` to verify all profile dirs exist.

**`cloak create` failed or captured the wrong account:**
Delete the bad profile dir (`rm -rf ~/.cloak/profiles/<name>`) and redo
Step 2/3 with the correct account logged in.

**cloak not found after `npm install -g`:**
Check that npm's global bin is on your PATH:
```sh
npm config get prefix   # e.g. /usr/local
ls $(npm config get prefix)/bin/cloak
```
Add `$(npm config get prefix)/bin` to your `fish_user_paths` if needed.
