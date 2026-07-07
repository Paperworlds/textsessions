---
slug: textsessions-checkpoint
owner: textsessions
status: implemented
version: 0.1.0
consumers: []
---
# textsessions session checkpoint log

## Summary

A structured YAML audit trail written per session, owned and managed by
textsessions. Before spawning a Claude Code session, textsessions creates a
checkpoint log file and injects its path via the `TS_CHECKPOINT_LOG`
environment variable. The running session appends `---`-delimited checkpoint
blocks at natural decision points. After the session exits, textsessions
appends a trailer block. No other tool writes to the file; consumers are
read-only.

## Motivation

Sessions — both agent runs and regular chats — produce no mid-run record of
what was decided or why. End-of-run summaries exist but miss inflection
points: phase completions, risky actions, blockers, direction changes. When
an agent drifts or wastes budget, there is no log to explain the path.

A per-session checkpoint file fills this gap without touching the session's
context window: the session *writes* to a file but never re-reads it, so
checkpoint overhead is context-free. At ~100–150 tokens per checkpoint block
and 3–7 blocks per session, the overhead is negligible against any session
long enough to benefit from an audit trail.

## Interface

### File location

```
~/.local/state/textsessions/checkpoints/<session-uuid>.yaml
```

`~/.local/state/` (not `~/.cache/`) because this file may contain
non-regenerable user-authored data (manual annotations, notes). The directory
is created automatically by textsessions on first write.

`<session-uuid>` matches the Claude Code session id used as the `.jsonl`
filename — the same join key as hints.

### Configuration

Opt-in. The global default is `false`; per-session config can override.

```yaml
# ~/.config/textsessions/config.yaml
checkpoint_log: false   # global default
```

A session config or hint file may set `checkpoint_log: true` to enable for
that session only. (Session config format is a separate concern; this spec
only defines the file contract once enabled.)

### File structure

A checkpoint log is a multi-document YAML file (documents separated by
`---`). It contains exactly one **header**, zero or more **checkpoint**
blocks appended during the session, and exactly one **trailer** appended
after exit.

#### Header (written by textsessions before spawn)

```yaml
checkpoint_log: "0.1.0"
session_id: "b2c3fcd9-7090-4216-b800-9ebf9782f03d"
started: "2026-05-05T09:14:00Z"
repo: textsessions
persona: agentic-pivot           # from hint file if present, else omitted
task: "implement ts jump command" # from session name or omitted
```

`checkpoint_log` is the schema version. Consumers MUST check this field and
ignore the file if the version is unsupported.

All fields except `checkpoint_log` and `session_id` are optional.

#### Checkpoint block (appended by the session)

```yaml
---
checkpoint: 1
timestamp: "2026-05-05T09:32:11Z"
phase: "implementation"
summary: "Extracted _resume_session helper, added jump_cmd skeleton"
references:
  - path: src/textsessions/cli.py
  - path: tests/test_jump.py
issues:
  - "Session filter logic needed an extra is_orphan guard"
next: "Wire --lead flag, add tests for no-match paths"
```

Fields:

| field | type | required | description |
|---|---|---|---|
| `checkpoint` | int | yes | monotonically increasing counter, starting at 1 |
| `timestamp` | str | yes | ISO-8601 UTC |
| `phase` | str | no | current phase name (free-form) |
| `summary` | str | yes | one-paragraph description of what just completed |
| `references` | list | no | files, paths, or URLs relevant to this checkpoint |
| `issues` | list[str] | no | surprises, constraints, workarounds encountered |
| `next` | str | no | intended next action after this checkpoint |

The session SHOULD write a checkpoint:
- When a logical phase completes (research done, code written, tests passing).
- Before a risky or irreversible action (force-push, drop table, large delete).
- When hitting a blocker or changing direction.
- At the end of work, before exiting.

The session MUST NOT re-read the log file. Writing is append-only and
context-free.

#### Trailer (written by textsessions after session exits)

```yaml
---
trailer: true
ended: "2026-05-05T10:02:44Z"
exit_code: 0
```

| field | type | required | description |
|---|---|---|---|
| `trailer` | bool | yes | always `true`; marks end of file |
| `ended` | str | yes | ISO-8601 UTC timestamp of process exit |
| `exit_code` | int | no | subprocess exit code if available |

### Environment variable

textsessions injects `TS_CHECKPOINT_LOG=<absolute-path>` into the session's
subprocess environment when the checkpoint log is enabled. The session uses
this path to locate the file for appending.

### System prompt injection

textsessions appends a brief instruction via `claude --append-system-prompt`
when `TS_CHECKPOINT_LOG` is set. The instruction tells the session:

1. What `TS_CHECKPOINT_LOG` is (a structured audit log it owns).
2. When to append a checkpoint block (phase complete / risky action / blocker /
   direction change / before exiting).
3. That it MUST NOT re-read the file.
4. The minimal required fields (`checkpoint`, `timestamp`, `summary`).

The full prompt text is a constant in textsessions source, versioned alongside
this spec.

### Integration point

The injection happens in `profiles.py` alongside the existing env-building
logic (`build_launch_env`). The `resume_cmd` function is extended to accept
an optional `checkpoint_log_path` and append `--append-system-prompt` to the
`claude` invocation when set. The caller (`_resume_session` in `cli.py`)
handles file creation and trailer writing.

## Surface in textsessions

- `load_sessions` / indexer: check whether
  `~/.local/state/textsessions/checkpoints/<sid>.yaml` exists and expose
  `session.has_checkpoint_log: bool`.
- TUI: show a small indicator (e.g. `[c]` column or chip) when the log is
  present.
- CLI: `ts checkpoint <name>` prints the parsed checkpoint log for a session
  (future; not in v0.1.0 scope).

## Conformance

A conforming **spawner** (textsessions itself) MUST:

1. Before spawning: create the log file with the header document.
2. Inject `TS_CHECKPOINT_LOG=<path>` into the subprocess environment.
3. Pass `--append-system-prompt <CHECKPOINT_SYSTEM_PROMPT>` to `claude`.
4. After exit: append the trailer document.
5. Mark the call-site with `# SPEC: textsessions-checkpoint`.
6. Declare in `docs/SPECS.yaml`:
   ```yaml
   owns:
     - slug: textsessions-checkpoint
       version: 0.1.0
       spec_path: docs/specs/textsessions-checkpoint.md
   ```

A conforming **session** (the Claude Code process) SHOULD:

1. Read `TS_CHECKPOINT_LOG` from the environment.
2. Append well-formed checkpoint documents at natural decision points.
3. Never read the file back during the session.
4. Include at minimum `checkpoint`, `timestamp`, and `summary` in each block.

The session is not a "conforming consumer" in the software sense — it has no
SPECS.yaml. The system prompt instruction is the mechanism for conveying
conformance expectations.

A conforming **consumer** reading the log MUST:

1. Treat the file as read-only.
2. Check `checkpoint_log` version in the header and skip unsupported versions.
3. Tolerate missing or malformed checkpoint documents without raising.
4. Not write to the file.

## Out of scope

- Real-time streaming or structured log tailing. The file is append-only YAML;
  tooling can `tail -f` it but this spec does not define a streaming protocol.
- Cross-session aggregation. Each file is scoped to one session UUID.
- Automatic checkpoint injection (hooking the Write/Edit/Bash tools). The
  session appends voluntarily based on the system prompt instruction.
- Checkpoint pruning or rotation. Log files are retained until the session
  entry is purged from the textsessions index.

## Open questions

1. **Opt-in granularity.** Should checkpoint logging be opt-in per session
   config, opt-in globally, or opt-out globally? v0.1.0 proposes opt-in
   (`checkpoint_log: false` default) to avoid noise on casual sessions.
   Revisit once there is real usage data.
2. **`ts checkpoint` read command.** A `ts checkpoint <name>` CLI to pretty-
   print a session's log is the obvious consumer surface. Out of scope for
   v0.1.0 but reserved as the natural v0.2.0 addition.
3. **Checkpoint log for resumed sessions.** If a session is resumed via
   `ts jump` or `ts sessions --resume`, should textsessions append to the
   existing log or create a new one? v0.1.0 proposes: create a new header
   with the same `session_id`, append to the existing file. The trailer from
   the previous run is still present. Consumers read the file as a sequence
   and see multiple header/trailer pairs.
4. **Manual checkpoints from the human side.** The thread notes that regular
   chats (not just agents) can benefit — the human appends checkpoint entries
   using the Write tool at decision points. This works with v0.1.0 as-is
   (same file, same schema), no spec change needed.
