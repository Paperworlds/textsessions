---
slug: textsessions-hints
owner: textsessions
status: adopted
version: 0.1.0
consumers:
- textprompts
adopted_at: '2026-05-03'
---
# textsessions session hints (persona, owner, labels)

## Summary

A small, optional, file-based contract that lets any tool annotate a Claude
Code session at launch time. textsessions reads these hints during indexing
and surfaces them as columns and filters (persona, owner, labels) without
needing to know anything about the producing tool.

The contract is owned by textsessions, but textsessions has no producer of
its own — it's purely a consumer of files anyone can write. Today the
intended producer is textprompts (`pp persona use` / `pp persona run`);
tomorrow other agents (textlives, textworld, ad-hoc scripts) can write the
same shape and benefit from the same surface.

## Motivation

`profile` (textaccounts) tells you *which auth* a session ran under.
`lineage.owner` (shallow-clone) tells you *which run owns this profile*.
Neither tells you *which persona* (or role, or workflow) is driving the
session — and personas multiply faster than profiles.

Today a single `personal` profile may host `paperworlds-writer`,
`agentic-pivot`, `job-scout` and more, all collapsed into one row in
textsessions. The triage layer was the answer to "sessions pile up";
personas pile up inside sessions — same problem one level deeper.

A second-class hint file pinned to the session UUID is enough to fix this
without coupling textsessions to any particular orchestrator.

## Interface

### Hint file location

```
~/.cache/textsessions/hints/<session-uuid>.yaml
```

`<session-uuid>` is the canonical Claude Code session id — the same UUID
used as the `.jsonl` filename in `~/.claude*/projects/<encoded-cwd>/`. It is
also exactly the value passed to `claude --session-id <uuid>` when launching
the session (introduced in Claude Code 2.x), which is the recommended way
producers correlate.

### Schema

All fields are optional; an empty or missing file is equivalent to no hint.

```yaml
persona: agentic-pivot                       # str  — display name of the persona
owner:   pp:persona:agentic-pivot:run-7      # str  — opaque owner identifier
labels:  [pivot, private]                    # list[str] — free-form labels
started: 2026-05-03T14:32:11Z                # str  — ISO-8601 launch timestamp (UTC)
```

`persona` is the user-facing label; one short token (slug-like preferred).

`owner` is an opaque string. textsessions displays it verbatim and uses it
for `--owner` filtering. Producers SHOULD use a structured form so other
tools can parse it if they need to (e.g. `pp:persona:<name>:<run-id>`,
`textworld:bot:<character>:<run-id>`), but textsessions itself does not
parse owner strings.

`labels` is free-form metadata. textsessions surfaces them as chips in the
TUI but does not impose a schema.

`started` is informational; textsessions prefers session start time from the
`.jsonl` itself, but uses `started` as a fallback when present.

### Producer responsibilities

A producer writing a hint MUST:

1. Decide the session UUID **before** spawning Claude Code (e.g. `uuid.uuid4()`).
2. Write the hint file *before* the `claude` process exits, ideally before it
   starts. The recommended pattern:
   ```python
   import uuid, yaml, pathlib, datetime, subprocess
   sid = str(uuid.uuid4())
   hint_dir = pathlib.Path("~/.cache/textsessions/hints").expanduser()
   hint_dir.mkdir(parents=True, exist_ok=True)
   (hint_dir / f"{sid}.yaml").write_text(yaml.safe_dump({
       "persona": "agentic-pivot",
       "owner":   "pp:persona:agentic-pivot:run-7",
       "started": datetime.datetime.now(datetime.UTC).isoformat(),
   }))
   subprocess.run(["claude", "--session-id", sid, ...])
   ```
3. Use `--session-id <sid>` when invoking `claude` so the JSONL filename
   matches the hint filename.

A producer SHOULD:

- Treat the hint as best-effort. A failure to write the hint MUST NOT block
  the session from launching.
- Not write hints for sessions it doesn't own (no scraping `~/.claude*` and
  back-filling). Hints are forward-looking, written at launch time only.

### Consumer responsibilities (textsessions itself)

textsessions during `build_index`:

1. For each session id it discovers, read
   `~/.cache/textsessions/hints/<sid>.yaml` if it exists.
2. Persist parsed values into the session entry under a `hint:` block (same
   pattern as `lineage:`).
3. Surface `persona`, `owner`, and `labels` in the CLI table, the TUI row,
   and the detail panel. Empty/missing fields render as empty cells; no
   warnings.
4. Provide filters:
   - `ts view --persona NAME`
   - `ts view --owner ID` (already exists for shallow lineage; should match
     hint-supplied owners too)
   - `ts view --label LABEL` (single-label match for v0.1.0)
5. Never write to the hint directory — consumers are read-only.

### Hint precedence vs lineage

When both a hint file and shallow-clone lineage are present:

- `persona` comes only from the hint file (lineage has no persona concept).
- `owner` is taken from the hint file if set, else from `lineage.owner`.
  textsessions presents one merged "owner" column.
- `labels` come only from the hint file.

This precedence keeps the hint as the authoritative per-session annotation
without breaking the existing lineage surface.

## Conformance

A conforming **producer** MUST:

1. Generate `<sid>` and pass `--session-id <sid>` to `claude`.
2. Write `~/.cache/textsessions/hints/<sid>.yaml` with at minimum a non-empty
   `persona` or `owner` field.
3. Mark the call-site with `# SPEC: textsessions-hints`.
4. Declare conformance in `docs/SPECS.yaml`:
   ```yaml
   follows:
     - slug: textsessions-hints
       pinned_version: "0.1.0"
       implemented_in:
         - src/<tool>/<file>.py
   ```

A conforming **consumer** (textsessions or any other reader) MUST:

1. Treat hint files as read-only and best-effort. Tolerate missing,
   unparseable, or malformed YAML by ignoring the hint without raising.
2. Not parse `owner` strings. Display them verbatim and match them by
   equality for `--owner` filtering.

## Out of scope

- Multiple personas per session. v0.1.0 is last-write-wins; if a session
  switches persona mid-run, that's not modelled. (Open question below.)
- Cross-machine sync. Hints live under `~/.cache/`, intentionally local.
- Garbage collection. textsessions can prune hints whose session UUID has
  been deleted from the index, but that's a separate concern from this
  contract.
- Mutation API. textsessions does not provide a CLI to write hints —
  producers write them directly.

## Open questions

1. **Multiple personas per session.** If `pp persona use A` is followed by
   `pp persona use B` in the same session, do we want a `personas: [A, B]`
   list, a `history:` log, or accept last-wins? v0.1.0 picks last-wins for
   simplicity; revisit when a real workflow demands more.
2. **`labels` cardinality.** Free-form is the v0.1.0 stance. If users adopt
   conventional label sets (e.g. `private`, `public`, `wip`), a curated
   vocabulary spec might emerge later.
3. **`pp persona run` (one-shot).** Should one-shot subagent runs get hints?
   Producer's call — they produce JSONL like any other session, so writing
   hints is harmless and useful for triage.
4. **Cache vs state directory.** `~/.cache/` was chosen because hints are
   regenerable and tied to ephemeral session IDs. If hints ever carry
   non-regenerable user-authored data (custom labels, notes), we'd want to
   move them to `~/.local/state/`.
