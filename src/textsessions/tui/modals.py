"""Modal dialogs for textsessions TUI."""

from __future__ import annotations

from dataclasses import dataclass

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static


@dataclass
class NewSessionResult:
    name: str
    priority: str
    profile: str
    repo_path: str  # path string of the selected repo


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
    """Modal to archive (soft) or delete (hard) a session.

    Enter/Space confirm archive (default safe action).
    Delete button triggers hard delete.
    """

    BINDINGS = [
        Binding("escape", "dismiss(None)", "Cancel"),
        Binding("enter", "confirm_archive", "Archive", show=False),
        Binding("space", "confirm_archive", "Archive", show=False),
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
            yield Label(f"[bold]Archive session?[/bold]  [dim](d=archive  D=delete)[/dim]{flag_str}", id="title")
            yield Static(
                f"[bold]{self._session_name}[/bold]\n\n"
                "[green]Archive[/green] tags as 'archived' — hidden from normal view, recoverable.\n"
                "[red]Delete[/red] removes permanently from the YAML index.",
                id="current",
            )
            with Horizontal(id="buttons"):
                yield Button("Archive (d)", variant="primary", id="archive")
                yield Button("Delete (D)", variant="error", id="delete")
                yield Button("Cancel", id="cancel")

    def action_confirm_archive(self) -> None:
        self.dismiss("archive")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "archive":
            self.dismiss("archive")
        elif event.button.id == "delete":
            self.dismiss("delete")
        else:
            self.dismiss(None)


class _DeleteConfirmModal(ModalScreen[bool]):
    """Short inline confirm for hard delete (D key)."""

    BINDINGS = [
        Binding("escape", "dismiss(False)", "Cancel"),
        Binding("y", "confirm_delete", "Yes", show=False),
        Binding("n", "dismiss(False)", "No", show=False),
    ]

    def __init__(self, session_name: str) -> None:
        super().__init__()
        self._session_name = session_name

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("[bold red]Permanently delete?[/bold red]  This cannot be undone.", id="title")
            yield Static(f"[bold]{self._session_name}[/bold]", id="current")
            with Horizontal(id="buttons"):
                yield Button("Delete [y]", variant="error", id="delete")
                yield Button("Cancel [n/Esc]", id="cancel")

    def action_confirm_delete(self) -> None:
        self.dismiss(True)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "delete")


class NewSessionModal(ModalScreen[NewSessionResult | None]):
    """Modal to launch a new Claude Code session with optional name and priority."""

    BINDINGS = [
        Binding("escape", "dismiss(None)", "Cancel"),
    ]

    PRIORITIES = [
        ("(none)", ""),
        ("H0 — critical", "H0"),
        ("1 — high", "1"),
        ("2 — medium", "2"),
        ("3 — low", "3"),
    ]

    def __init__(self, profiles: list[str], default_profile: str, default_repo_path: str) -> None:
        super().__init__()
        self._profiles = profiles
        self._default_profile = default_profile
        self._default_repo_path = default_repo_path

    def compose(self) -> ComposeResult:
        profile_options = [(p, p) for p in self._profiles]
        with Vertical(id="dialog"):
            yield Label("[bold]New session[/bold]", id="title")
            yield Label("Name (optional):")
            yield Input(placeholder="e.g. refactor-auth", id="name-input")
            yield Label("Priority:")
            yield Select(self.PRIORITIES, id="priority-select", allow_blank=False, value="")
            yield Label("Profile:")
            yield Select(profile_options, id="profile-select", allow_blank=False,
                         value=self._default_profile)
            with Horizontal(id="buttons"):
                yield Button("Launch", variant="primary", id="launch")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "launch":
            name = self.query_one("#name-input", Input).value.strip()
            priority_val = self.query_one("#priority-select", Select).value
            profile_val = self.query_one("#profile-select", Select).value
            priority = str(priority_val) if priority_val and priority_val is not Select.BLANK else ""
            profile = str(profile_val) if profile_val and profile_val is not Select.BLANK else self._default_profile
            self.dismiss(NewSessionResult(
                name=name,
                priority=priority,
                profile=profile,
                repo_path=self._default_repo_path,
            ))
        else:
            self.dismiss(None)

    def on_input_submitted(self, _event: Input.Submitted) -> None:
        # Enter in name field moves focus to launch button
        self.query_one("#launch", Button).focus()
