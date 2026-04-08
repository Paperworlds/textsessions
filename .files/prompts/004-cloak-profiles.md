---
id: "004"
title: "Cloak profile integration and textsessions profile commands"
repo: textsessions
model: sonnet
budget_usd: 3.00
max_turns: 80
depends_on: ["003"]
---

## Context

Claude Code sessions belong to a profile (work, personal, default, etc.).
Without any profile tool, all sessions share a single Claude config dir and
a single account. `cloak` (https://github.com/synth1s/cloak) solves this by
isolating each profile in `~/.cloak/profiles/<name>/` and switching via the
`CLAUDE_CONFIG_DIR` environment variable.

`textsessions` already stores a `profile` field per repo in config. This
maps directly to a cloak profile name. The integration is purely:

```python
env = os.environ.copy()
if cloak_available() and profile != "default":
    env["CLAUDE_CONFIG_DIR"] = str(Path.home() / ".cloak" / "profiles" / profile)
subprocess.run(cmd, env=env)
```

If cloak is not installed, this block is skipped and sessions launch with
the default Claude config. The feature is opt-in and non-breaking.

Similarly, `ai-proxy` (the token proxy at `localhost:7474`) should be
injected into the subprocess env when detected as installed/running:

```python
if aiproxy_available():
    env["ANTHROPIC_BASE_URL"] = "http://localhost:7474"
```

## Profile detection helpers

Add `textsessions/profiles.py`:

```python
def cloak_available() -> bool:
    """True if cloak is installed (binary on PATH)."""

def cloak_profile_dir(profile: str) -> Path | None:
    """Return ~/.cloak/profiles/<profile> if it exists, else None."""

def list_cloak_profiles() -> list[str]:
    """Return sorted list of profile names found in ~/.cloak/profiles/."""

def aiproxy_available() -> bool:
    """True if ai-proxy binary is on PATH."""

def aiproxy_running() -> bool:
    """True if localhost:7474 is responding (quick socket check, <100ms timeout)."""
```

## Subprocess env in `app.py`

Add `_build_launch_env(profile: str) -> dict` that applies both integrations.
Use it in `action_resume_session` and `action_new_session`.

## Config changes

Add to `Config`:

```toml
[integrations]
cloak = true       # auto-detected if omitted; set false to disable explicitly
aiproxy = true     # auto-detected if omitted; set false to disable explicitly
```

`cloak = true` means "use cloak if available". The config never hardcodes
paths — detection is always runtime.

Load/save these in `config.py` as an `IntegrationsConfig` dataclass.

## `textsessions profile` subcommands

```
textsessions profile status
```
Show integration status:
```
Cloak:    installed (v0.x.x)  3 profiles: default, personal, work
ai-proxy: installed, running (localhost:7474)
```
If not installed, show install hint:
```
Cloak:    not installed — run: npm install -g @synth1s/cloak
```

```
textsessions profile list
```
List cloak profiles with which repos use them:
```
default    mono
personal   data, textlives, textworld
work       (none configured)
```
If cloak is not installed, explain that profiles still exist in textsessions
config but won't be isolated until cloak is set up.

```
textsessions profile setup <name>
```
Guides the user through creating a cloak profile:
1. Checks cloak is installed; if not, prints install instructions and exits.
2. Runs `cloak create <name>` interactively (or prints the command to run
   manually, since it requires an interactive login — do NOT shell out to it
   automatically).
3. Verifies `~/.cloak/profiles/<name>/` was created.
4. Prints confirmation.

```
textsessions profile check
```
For each profile used in the config, verify a cloak profile dir exists.
Report any missing ones with setup instructions.

## TUI footer hint

When cloak is not installed and a repo with a non-default profile is selected,
show a dim hint in the right panel below the session detail:

```
[dim]Profiles: install cloak for isolation (textsessions profile status)[/dim]
```

Only show once — don't spam it per session.

## Tests

- `tests/test_profiles.py`:
  - `test_cloak_available_false` — mock PATH with no cloak binary
  - `test_cloak_available_true` — mock PATH with fake cloak binary
  - `test_list_cloak_profiles` — synthetic `~/.cloak/profiles/` in tmp_path
  - `test_aiproxy_running_false` — nothing on 7474
  - `test_build_launch_env_no_cloak` — env has no CLAUDE_CONFIG_DIR
  - `test_build_launch_env_with_cloak` — env has correct CLAUDE_CONFIG_DIR
  - `test_build_launch_env_with_aiproxy` — env has ANTHROPIC_BASE_URL

## Notes

- Never auto-install cloak or ai-proxy. Only detect and guide.
- `textsessions profile setup` must not auto-run `cloak create` headlessly —
  cloak requires an interactive browser-based OAuth login. Print the command
  for the user to run themselves.
- `aiproxy_running()` is best-effort. If the check takes >100ms, skip it and
  treat as not running.
- The `default` profile never sets `CLAUDE_CONFIG_DIR` (uses system default).
