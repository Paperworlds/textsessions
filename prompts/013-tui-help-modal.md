---
id: "013"
title: "TUI: ? key shows help modal with all keybindings"
repo: textsessions
phase: "phase-1"
model: sonnet
budget_usd: 1.00
max_turns: 20
depends_on: ["002"]
---

## Context

The TUI has no inline help. The Footer shows some bindings but is truncated on
narrow terminals. New users and returning users after a gap have no way to discover
keybindings without reading the source.

## Task

### 1. Add `?` binding in `tui/app.py`

```python
Binding("?", "show_help", "Help"),
```

### 2. Add `HelpModal` in `tui/modals.py`

A read-only modal that lists all bindings in two columns (key | description).

```python
class HelpModal(ModalScreen[None]):
    """Show all keybindings."""

    BINDINGS = [
        Binding("escape", "dismiss(None)", "Close"),
        Binding("?", "dismiss(None)", "Close"),
        Binding("q", "dismiss(None)", "Close"),
    ]

    HELP_ROWS = [
        ("enter / click", "Resume session"),
        ("n",             "New session"),
        ("r",             "Rename session"),
        ("t",             "Tag session"),
        ("p",             "Set priority"),
        ("x",             "Pin / unpin"),
        ("d",             "Archive session"),
        ("D",             "Delete session"),
        ("a",             "Toggle all repos / current folder"),
        ("s",             "Toggle sort (date / priority)"),
        ("g",             "Toggle ghosts"),
        ("ctrl+r",        "Reindex current scope"),
        ("/",             "Focus filter"),
        ("escape",        "Clear filter"),
        ("?",             "This help"),
        ("q",             "Quit"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("[bold]Keybindings[/bold]", id="title")
            for key, desc in self.HELP_ROWS:
                yield Static(f"  [bold cyan]{key:<14}[/bold cyan] {desc}")
            yield Static("")
            yield Static("[dim]press ?, escape, or q to close[/dim]")
```

Keep the dialog styled like existing modals (uses `#dialog` CSS id).

### 3. Add `action_show_help` in `tui/app.py`

```python
def action_show_help(self) -> None:
    from .modals import HelpModal
    self.push_screen(HelpModal())
```

### 4. Import and export

Export `HelpModal` from `modals.py` alongside the other modals. Import it lazily
inside `action_show_help` (same pattern as other modals in this file) or add it
to the existing top-level import.

### 5. Keep HELP_ROWS in sync with actual bindings

The `HELP_ROWS` list is manually maintained — it is intentionally simple.
No need to auto-derive from `BINDINGS`. Just keep it accurate.

### 6. Tests

No new tests needed. Verify existing tests pass.
