"""Standalone config app for managing repos in textsessions."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Select, Static

from ..config import Config, RepoConfig, load, save

_HOME = Path.home()


def _short_path(path: Path) -> str:
    try:
        return "~/" + str(path.relative_to(_HOME))
    except ValueError:
        return str(path)


def _render_detail(repo: RepoConfig | None) -> str:
    if repo is None:
        return (
            "[dim]No repos configured.[/dim]\n\n"
            "Press [bold]a[/bold] to add a repo."
        )
    lines = [
        f"[bold]{repo.label}[/bold]",
        "",
        f"[bold]Path:[/bold]      {_short_path(repo.path)}",
        f"[bold]Profile:[/bold]   {repo.profile}",
        f"[bold]Recursive:[/bold] {'yes' if repo.recursive else 'no'}",
    ]
    if not repo.path.exists():
        lines.insert(0, "[bold red]path not found[/bold red]")
    elif not (repo.path / ".git").exists() and not repo.recursive:
        lines.insert(0, "[yellow]not a git repo[/yellow]")
    return "\n".join(lines)


def _available_profiles() -> list[str]:
    try:
        from textaccounts.api import list_profiles
        profiles = list_profiles()
        if profiles:
            return profiles
    except ImportError:
        pass
    return ["default"]


class EditLabelModal(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "dismiss(None)", "Cancel")]

    def __init__(self, current: str) -> None:
        super().__init__()
        self._current = current

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("[bold]Edit label[/bold]", id="title")
            yield Input(value=self._current, id="label-input")
            with Horizontal(id="buttons"):
                yield Button("Save", variant="primary", id="save")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            self.dismiss(self.query_one("#label-input", Input).value.strip())
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip())


class EditProfileModal(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "dismiss(None)", "Cancel")]

    def __init__(self, current: str) -> None:
        super().__init__()
        self._current = current

    def compose(self) -> ComposeResult:
        profiles = _available_profiles()
        if self._current not in profiles:
            profiles.append(self._current)
        options = [(p, p) for p in profiles]
        with Vertical(id="dialog"):
            yield Label("[bold]Edit profile[/bold]", id="title")
            yield Select(options, value=self._current, id="profile-select")
            with Horizontal(id="buttons"):
                yield Button("Save", variant="primary", id="save")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            val = self.query_one("#profile-select", Select).value
            self.dismiss(str(val) if val != Select.BLANK else None)
        else:
            self.dismiss(None)


class AddRepoModal(ModalScreen["tuple[str, str, str] | None"]):
    """Returns (path, label, profile) or None."""
    BINDINGS = [Binding("escape", "dismiss(None)", "Cancel")]

    def compose(self) -> ComposeResult:
        profiles = _available_profiles()
        options = [(p, p) for p in profiles]
        with Vertical(id="dialog"):
            yield Label("[bold]Add repo[/bold]", id="title")
            yield Label("Path:")
            yield Input(placeholder="/path/to/repo", id="path-input")
            yield Label("Label:")
            yield Input(placeholder="(auto from dirname)", id="label-input")
            yield Label("Profile:")
            yield Select(options, value=profiles[0], id="profile-select")
            with Horizontal(id="buttons"):
                yield Button("Add", variant="primary", id="save")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            path = self.query_one("#path-input", Input).value.strip()
            label = self.query_one("#label-input", Input).value.strip()
            profile = self.query_one("#profile-select", Select).value
            if path:
                self.dismiss((path, label, str(profile) if profile != Select.BLANK else "default"))
            else:
                self.dismiss(None)
        else:
            self.dismiss(None)


class DeleteConfirmModal(ModalScreen[bool]):
    BINDINGS = [Binding("escape", "dismiss(False)", "Cancel")]

    def __init__(self, label: str) -> None:
        super().__init__()
        self._label = label

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(f"[bold]Remove repo:[/bold] {self._label}", id="title")
            yield Static("[dim]This removes it from config only — no files are deleted.[/dim]")
            with Horizontal(id="buttons"):
                yield Button("Remove", variant="error", id="save")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "save")


class ConfigApp(App):
    """Standalone app for managing repo configuration."""

    CSS = """
    Screen {
        layout: vertical;
    }
    #config-main {
        layout: horizontal;
        height: 1fr;
    }
    #config-left {
        width: 70%;
        border: solid $primary;
        padding: 0 1;
    }
    #config-right {
        width: 30%;
        border: solid $primary-darken-2;
        padding: 1;
    }
    #config-title {
        margin-bottom: 1;
        color: $text;
        text-style: bold;
    }
    #config-table {
        height: 1fr;
    }
    #config-detail {
        height: 1fr;
    }
    #dialog {
        background: $surface;
        border: solid $primary;
        padding: 1 2;
        width: 60;
        height: auto;
    }
    #title {
        text-style: bold;
        margin-bottom: 1;
    }
    #buttons {
        margin-top: 1;
        height: 3;
        align: right middle;
    }
    Button {
        margin-left: 1;
    }
    """

    BINDINGS = [
        Binding("e", "edit_label", "Label"),
        Binding("p", "edit_profile", "Profile"),
        Binding("d", "delete_repo", "Remove"),
        Binding("a", "add_repo", "Add"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="config-main"):
            with Vertical(id="config-left"):
                yield Label("Repo Configuration", id="config-title")
                yield DataTable(id="config-table", cursor_type="row")
            with ScrollableContainer(id="config-right"):
                yield Static("", id="config-detail")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh()
        self.query_one("#config-table", DataTable).focus()

    def _refresh(self) -> None:
        table = self.query_one("#config-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Label", "Path", "Profile", "Rec")
        for repo in self._config.repos:
            rec = "yes" if repo.recursive else ""
            table.add_row(
                repo.label,
                _short_path(repo.path),
                repo.profile,
                rec,
                key=str(repo.path),
            )
        self._update_detail()

    def _current_repo(self) -> RepoConfig | None:
        table = self.query_one("#config-table", DataTable)
        if table.row_count == 0:
            return None
        try:
            row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        except Exception:
            return None
        path = Path(row_key.value)
        for r in self._config.repos:
            if r.path == path:
                return r
        return None

    def _update_detail(self) -> None:
        detail = self.query_one("#config-detail", Static)
        detail.update(_render_detail(self._current_repo()))

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._update_detail()

    def action_edit_label(self) -> None:
        repo = self._current_repo()
        if not repo:
            return

        def handle(result: str | None) -> None:
            if result and result != repo.label:
                repo.label = result
                save(self._config)
                self._refresh()
                self.notify(f"Label → {result}")

        self.push_screen(EditLabelModal(repo.label), handle)

    def action_edit_profile(self) -> None:
        repo = self._current_repo()
        if not repo:
            return

        def handle(result: str | None) -> None:
            if result and result != repo.profile:
                repo.profile = result
                save(self._config)
                self._refresh()
                self.notify(f"Profile → {result}")

        self.push_screen(EditProfileModal(repo.profile), handle)

    def action_delete_repo(self) -> None:
        repo = self._current_repo()
        if not repo:
            return

        def handle(confirmed: bool) -> None:
            if confirmed:
                self._config.repos = [r for r in self._config.repos if r.path != repo.path]
                save(self._config)
                self._refresh()
                self.notify(f"Removed {repo.label}")

        self.push_screen(DeleteConfirmModal(repo.label), handle)

    def action_add_repo(self) -> None:
        def handle(result: "tuple[str, str, str] | None") -> None:
            if result is None:
                return
            path_str, label, profile = result
            path = Path(path_str).expanduser().resolve()
            if not path.is_dir():
                self.notify(f"Not a directory: {path}", severity="error")
                return
            existing = {r.path for r in self._config.repos}
            if path in existing:
                self.notify(f"Already configured: {path}", severity="warning")
                return
            repo_label = label or path.name
            self._config.repos.append(RepoConfig(path=path, label=repo_label, profile=profile))
            save(self._config)
            self._refresh()
            self.notify(f"Added {repo_label}")

        self.push_screen(AddRepoModal(), handle)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Enter on a row opens edit-label modal (same as 'e')."""
        self.action_edit_label()
