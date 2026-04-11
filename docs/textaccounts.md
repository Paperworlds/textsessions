# textaccounts — Profile Management

textsessions uses **textaccounts** to manage multiple Claude Code accounts and configurations. Each profile is a complete, isolated config directory, preserving session history, memory, and credentials separately.

## Quick Start

### Installation

textaccounts ships as part of textsessions:

```sh
pipx install textsessions
```

### Register existing directories

If you already have Claude config directories (e.g. `~/.claude-work`, `~/.claude-personal`), register them without copying any data:

```sh
textaccounts adopt work ~/.claude-work
textaccounts adopt personal ~/.claude-personal
textaccounts list   # verify profiles
```

### Switch profiles

Use the `ta` wrapper function to switch profiles in fish:

```fish
ta switch work     # sets CLAUDE_CONFIG_DIR, preserves session history
```

The `ta` function sources completions automatically — just add this to `~/.config/fish/config.fish`:

```fish
source /path/to/textsessions/completions/ta.fish
```

## Full Documentation

For complete CLI reference, config schema, and design decisions, see the [textaccounts README](../src/textaccounts/README.md).

## Why textaccounts?

- **Full directory isolation** — Each profile is a complete `~/.claude/` directory, not just 2 files
- **Preserved sessions** — Session history, project memory, and agent state stay with their profile
- **Native adoption** — Register existing directories without moving or copying
- **Fish-native** — `ta switch` sets environment variables correctly in the shell
