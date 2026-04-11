"""Interactive profile view for textaccounts."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Static

from textaccounts import core
from textaccounts.config import CONFIG_PATH, load_registry, save_registry


def _fmt_size(size_bytes: int) -> str:
    kb = size_bytes // 1024
    return f"{kb // 1024}M" if kb > 1024 else f"{kb}K"


def _render_detail(profile: dict | None) -> str:
    if profile is None:
        return "[dim]No profile selected[/dim]"
    lines = []
    if profile["active"]:
        lines.append("[bold green]● active[/bold green]")
    lines.append(f"[bold]{profile['name']}[/bold]")
    lines.append(f"Path:     {profile['path']}")
    if profile["email"]:
        lines.append(f"Email:    {profile['email']}")
    lines.append(f"Sessions: {profile['sessions']}")
    lines.append(f"Size:     {_fmt_size(profile['dir_size'])}")
    if profile["worker"]:
        lines.append("[dim]worker (auth-only copy)[/dim]")
    return "\n".join(lines)


class AdoptModal(ModalScreen["tuple[str, str] | None"]):
    BINDINGS = [Binding("escape", "dismiss(None)", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("[bold]Adopt existing Claude config dir[/bold]", id="title")
            yield Label("Profile name:")
            yield Input(placeholder="e.g. work", id="name-input")
            yield Label("Path:")
            yield Input(placeholder="e.g. ~/.claude-work", id="path-input")
            with Horizontal(id="buttons"):
                yield Button("Adopt", variant="primary", id="adopt-btn")
                yield Button("Cancel", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "adopt-btn":
            self._submit()
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "name-input":
            self.query_one("#path-input", Input).focus()
        else:
            self._submit()

    def _submit(self) -> None:
        name = self.query_one("#name-input", Input).value.strip()
        path = self.query_one("#path-input", Input).value.strip()
        self.dismiss((name, path) if name and path else None)


class TextAccountsApp(App):
    CSS = """
    Screen { layout: horizontal; }
    #profiles {
        width: 3fr;
        border: solid $primary;
    }
    #detail {
        width: 2fr;
        padding: 1 2;
        border: solid $surface;
    }
    AdoptModal #dialog {
        width: 60;
        padding: 1 2;
        background: $surface;
        border: solid $primary;
        margin: 4 8;
    }
    AdoptModal #title { margin-bottom: 1; }
    AdoptModal #buttons { margin-top: 1; align-horizontal: right; }
    """

    TITLE = "textaccounts"

    BINDINGS = [
        Binding("s", "switch_profile", "Switch"),
        Binding("a", "adopt", "Adopt"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, config_path: Path = CONFIG_PATH) -> None:
        super().__init__()
        self._config_path = config_path
        self._profiles: list[dict] = []

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield DataTable(id="profiles", cursor_type="row")
            yield Static(id="detail")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        registry = load_registry(self._config_path)
        self._profiles = core.list_profiles(registry)
        table = self.query_one(DataTable)
        table.clear(columns=True)
        table.add_columns("", "Name", "Path", "Email", "Sessions", "Size")
        for p in self._profiles:
            marker = "*" if p["active"] else ""
            size = _fmt_size(p["dir_size"])
            name_col = p["name"] + (" [worker]" if p["worker"] else "")
            table.add_row(marker, name_col, str(p["path"]), p["email"] or "", str(p["sessions"]), size)
        self._update_detail()

    def _selected_profile(self) -> dict | None:
        table = self.query_one(DataTable)
        idx = table.cursor_row
        if 0 <= idx < len(self._profiles):
            return self._profiles[idx]
        return None

    def _update_detail(self) -> None:
        self.query_one("#detail", Static).update(_render_detail(self._selected_profile()))

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._update_detail()

    def action_switch_profile(self) -> None:
        profile = self._selected_profile()
        if profile is None:
            return
        name = profile["name"]
        try:
            registry = load_registry(self._config_path)
            core.switch(name, registry)
            save_registry(registry, self._config_path)
            self._refresh()
            self.notify(f"Active: {name} — run: ta switch {name}", timeout=6)
        except Exception as e:
            self.notify(str(e), severity="error")

    def action_adopt(self) -> None:
        def handle(result: tuple[str, str] | None) -> None:
            if result is None:
                return
            name, path_str = result
            try:
                registry = load_registry(self._config_path)
                core.adopt(name, Path(path_str).expanduser(), registry)
                save_registry(registry, self._config_path)
                self._refresh()
                self.notify(f"Adopted: {name}")
            except Exception as e:
                self.notify(str(e), severity="error")

        self.push_screen(AdoptModal(), handle)
