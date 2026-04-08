"""Modal dialogs for textsessions TUI."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static


class TagModal(ModalScreen[str | None]):
    """Modal to add/remove tags on a session."""

    BINDINGS = [
        Binding("escape", "dismiss(None)", "Cancel"),
    ]

    def __init__(self, session_name: str, current_tags: list[str]) -> None:
        super().__init__()
        self._session_name = session_name
        self._current_tags = current_tags

    def compose(self) -> ComposeResult:
        tags_str = ", ".join(self._current_tags)
        with Vertical(id="dialog"):
            yield Label(f"[bold]Tags[/bold] — {self._session_name}", id="title")
            yield Static(f"Current: {tags_str or '(none)'}", id="current")
            yield Label("New tags (comma-separated, prefix with - to remove):")
            yield Input(placeholder="e.g. daily, recurrent or -old", id="tag-input")
            with Horizontal(id="buttons"):
                yield Button("Save", variant="primary", id="save")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            self.dismiss(self.query_one("#tag-input", Input).value)
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)


class PriorityModal(ModalScreen[str | None]):
    """Modal to set session priority."""

    BINDINGS = [
        Binding("escape", "dismiss(None)", "Cancel"),
    ]

    PRIORITIES = [
        ("H0 — critical", "H0"),
        ("1 — high", "1"),
        ("2 — medium", "2"),
        ("3 — low", "3"),
        ("clear — remove", "clear"),
    ]

    def __init__(self, session_name: str, current_priority: str) -> None:
        super().__init__()
        self._session_name = session_name
        self._current = current_priority

    def compose(self) -> ComposeResult:
        options = [(label, val) for label, val in self.PRIORITIES]
        with Vertical(id="dialog"):
            yield Label(f"[bold]Priority[/bold] — {self._session_name}", id="title")
            yield Static(f"Current: {self._current or '(none)'}", id="current")
            yield Select(options, id="priority-select", allow_blank=False,
                         value=self._current if self._current else Select.BLANK)
            with Horizontal(id="buttons"):
                yield Button("Save", variant="primary", id="save")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            val = self.query_one("#priority-select", Select).value
            self.dismiss(str(val) if val and val is not Select.BLANK else None)
        else:
            self.dismiss(None)


class RenameModal(ModalScreen[str | None]):
    """Modal to rename a session."""

    BINDINGS = [
        Binding("escape", "dismiss(None)", "Cancel"),
    ]

    def __init__(self, session_name: str, current_slug: str) -> None:
        super().__init__()
        self._session_name = session_name
        self._current_slug = current_slug

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(f"[bold]Rename[/bold] — {self._session_name}", id="title")
            yield Input(value=self._current_slug[:60], id="rename-input")
            with Horizontal(id="buttons"):
                yield Button("Save", variant="primary", id="save")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            self.dismiss(self.query_one("#rename-input", Input).value.strip())
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        val = event.value.strip()
        self.dismiss(val if val else None)


class ArchiveModal(ModalScreen[str | None]):
    """Modal to hide or delete a session."""

    BINDINGS = [
        Binding("escape", "dismiss(None)", "Cancel"),
    ]

    def __init__(self, session_name: str, is_ghost: bool, is_orphan: bool) -> None:
        super().__init__()
        self._session_name = session_name
        self._is_ghost = is_ghost
        self._is_orphan = is_orphan

    def compose(self) -> ComposeResult:
        flags = []
        if self._is_ghost:
            flags.append("[red]ghost[/red]")
        if self._is_orphan:
            flags.append("[yellow]orphan[/yellow]")
        flag_str = "  " + "  ".join(flags) if flags else ""
        with Vertical(id="dialog"):
            yield Label(f"[bold]Archive / Delete[/bold] — {self._session_name}{flag_str}", id="title")
            yield Static(
                "[dim]Hide[/dim] keeps the session in the index but filters it out.\n"
                "[dim]Delete[/dim] removes it permanently from the YAML index.",
                id="current",
            )
            with Horizontal(id="buttons"):
                yield Button("Hide", variant="warning", id="hide")
                yield Button("Delete", variant="error", id="delete")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "hide":
            self.dismiss("hide")
        elif event.button.id == "delete":
            self.dismiss("delete")
        else:
            self.dismiss(None)
