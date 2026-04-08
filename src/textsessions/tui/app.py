"""Main Textual application for textsessions."""

from __future__ import annotations

import subprocess
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Static,
    TabbedContent,
    TabPane,
)

from ..config import Config, load, repo_key
from ..proxy import SessionStats, fmt_tokens, load_current_session
from ..sessions import Session, delete_session_from_index, filter_sessions, load_sessions, sort_by_priority
from .modals import ArchiveModal, PriorityModal, RenameModal, TagModal

SESSIONS_INDEX = "claude-sessions-index"
PRIORITY_COLORS = {"H0": "bold red", "1": "yellow", "2": "cyan", "3": "dim", "": ""}


class SessionDetail(Static):
    """Right panel showing selected session detail + token stats."""

    session: reactive[Session | None] = reactive(None)
    proxy_stats: reactive[SessionStats] = reactive(SessionStats())

    def render(self) -> str:
        s = self.session
        stats = self.proxy_stats
        if s is None:
            return "[dim]Select a session to see details[/dim]"

        pri = s.display_priority
        pri_str = f"[bold red]{pri}[/bold red]" if pri.startswith("H") else (f"[yellow]{pri}[/yellow]" if pri else "[dim]—[/dim]")
        tags_str = "  ".join(f"[cyan]#{t}[/cyan]" for t in s.tags) if s.tags else "[dim](none)[/dim]"

        slug_lines = []
        slug = s.slug
        while len(slug) > 50:
            slug_lines.append(slug[:50])
            slug = slug[50:]
        slug_lines.append(slug)
        slug_display = "\n           ".join(slug_lines)

        lines = [
            f"[bold]Name:[/bold]    {s.name}",
            f"[bold]Repo:[/bold]    {s.repo_label}",
            f"[bold]Profile:[/bold] {s.profile}",
            f"[bold]Tags:[/bold]    {tags_str}",
            f"[bold]Priority:[/bold]{pri_str}",
            f"[bold]Active:[/bold]  {s.last_active}",
            f"[bold]ID:[/bold]      [dim]{s.id}[/dim]",
            "",
            f"[bold]Slug:[/bold]    [dim]{slug_display}[/dim]",
            "",
            "─" * 40,
            "[bold]Token Proxy (current session)[/bold]",
        ]

        if stats.is_live:
            lines += [
                f"  Input:    [green]{fmt_tokens(stats.input_tokens)}[/green]   Output: [green]{fmt_tokens(stats.output_tokens)}[/green]",
                f"  Requests: [green]{stats.requests}[/green]         Cost:   [green]${stats.cost_usd:.3f}[/green]",
            ]
        else:
            lines.append("  [dim]Proxy not running or no data[/dim]")

        return "\n".join(lines)


class TextSessionsApp(App):
    """Main TUI application."""

    CSS = """
    Screen {
        layout: vertical;
    }
    #main {
        layout: horizontal;
        height: 1fr;
    }
    #left-panel {
        width: 60%;
        border: solid $primary;
        padding: 0 1;
    }
    #right-panel {
        width: 40%;
        border: solid $primary-darken-2;
        padding: 1;
    }
    #filter-input {
        margin-bottom: 1;
        height: 3;
    }
    DataTable {
        height: 1fr;
    }
    SessionDetail {
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
    #current {
        color: $text-muted;
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
        Binding("t", "tag_session", "Tag"),
        Binding("p", "priority_session", "Priority"),
        Binding("r", "rename_session", "Rename"),
        Binding("d", "archive_session", "Archive/Delete"),
        Binding("enter", "resume_session", "Resume", show=True),
        Binding("/", "focus_filter", "Filter"),
        Binding("s", "toggle_sort", "Sort"),
        Binding("g", "toggle_ghosts", "Ghosts"),
        Binding("escape", "clear_filter", "Clear filter"),
        Binding("q", "quit", "Quit"),
    ]

    _sort_by_priority: reactive[bool] = reactive(False)
    _ghosts_only: reactive[bool] = reactive(False)
    _filter_query: reactive[str] = reactive("")
    _sessions: list[Session] = []
    _filtered: list[Session] = []
    _config: Config

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main"):
            with Vertical(id="left-panel"):
                yield Input(placeholder="/ to filter…", id="filter-input")
                yield DataTable(id="sessions-table", cursor_type="row")
            with ScrollableContainer(id="right-panel"):
                yield SessionDetail(id="detail")
        yield Footer()

    def on_mount(self) -> None:
        self._reload_sessions()
        self._populate_table()
        self.set_interval(5, self._refresh_proxy)
        self._refresh_proxy()

    def _reload_sessions(self) -> None:
        self._sessions = load_sessions(self._config)
        self._apply_filter()

    def _apply_filter(self) -> None:
        q = self._filter_query
        self._filtered = filter_sessions(self._sessions, query=q, ghosts_only=self._ghosts_only)
        if self._sort_by_priority:
            self._filtered = sort_by_priority(self._filtered)

    def _populate_table(self) -> None:
        table = self.query_one("#sessions-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Name", "Repo", "Profile", "Tags", "Pri", "Last Active")
        for s in self._filtered:
            pri = s.display_priority
            if s.is_ghost:
                name_cell = f"[dim]~{s.name}[/dim]"
            elif s.is_orphan:
                name_cell = f"[dim]{s.name}[/dim]"
            else:
                name_cell = s.name
            table.add_row(
                name_cell,
                s.repo_label,
                s.profile,
                " ".join(f"#{t}" for t in s.tags if t != "archived"),
                pri,
                s.last_active,
                key=s.id,
            )
        # Re-select first row if available
        if self._filtered:
            table.move_cursor(row=0)
            self._update_detail(0)

    def _update_detail(self, row_index: int) -> None:
        detail = self.query_one("#detail", SessionDetail)
        if 0 <= row_index < len(self._filtered):
            detail.session = self._filtered[row_index]

    def _refresh_proxy(self) -> None:
        detail = self.query_one("#detail", SessionDetail)
        detail.proxy_stats = load_current_session(self._config.proxy)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._update_detail(event.cursor_row)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "filter-input":
            self._filter_query = event.value
            self._apply_filter()
            self._populate_table()

    def action_focus_filter(self) -> None:
        self.query_one("#filter-input", Input).focus()

    def action_clear_filter(self) -> None:
        inp = self.query_one("#filter-input", Input)
        inp.value = ""
        self.query_one("#sessions-table", DataTable).focus()

    def action_toggle_sort(self) -> None:
        self._sort_by_priority = not self._sort_by_priority
        self._apply_filter()
        self._populate_table()

    def action_toggle_ghosts(self) -> None:
        self._ghosts_only = not self._ghosts_only
        self._apply_filter()
        self._populate_table()

    def _current_session(self) -> Session | None:
        table = self.query_one("#sessions-table", DataTable)
        row = table.cursor_row
        if 0 <= row < len(self._filtered):
            return self._filtered[row]
        return None

    def action_tag_session(self) -> None:
        s = self._current_session()
        if not s:
            return

        def handle(result: str | None) -> None:
            if not result:
                return
            key = repo_key(s.repo_path)
            parts = [t.strip() for t in result.split(",") if t.strip()]
            to_add = [t for t in parts if not t.startswith("-")]
            to_remove = [t[1:] for t in parts if t.startswith("-")]
            if to_add:
                subprocess.run([SESSIONS_INDEX, "tag", key, s.id, ",".join(to_add)], capture_output=True)
            if to_remove:
                subprocess.run([SESSIONS_INDEX, "untag", key, s.id, ",".join(to_remove)], capture_output=True)
            self._reload_sessions()
            self._populate_table()

        self.push_screen(TagModal(s.name, s.tags), handle)

    def action_priority_session(self) -> None:
        s = self._current_session()
        if not s:
            return

        def handle(result: str | None) -> None:
            if not result:
                return
            key = repo_key(s.repo_path)
            subprocess.run([SESSIONS_INDEX, "priority", key, s.id, result], capture_output=True)
            self._reload_sessions()
            self._populate_table()

        self.push_screen(PriorityModal(s.name, s.priority), handle)

    def action_rename_session(self) -> None:
        s = self._current_session()
        if not s:
            return

        def handle(result: str | None) -> None:
            if not result:
                return
            key = repo_key(s.repo_path)
            subprocess.run([SESSIONS_INDEX, "rename", key, s.id, result], capture_output=True)
            self._reload_sessions()
            self._populate_table()

        self.push_screen(RenameModal(s.name, s.slug), handle)

    def action_archive_session(self) -> None:
        s = self._current_session()
        if not s:
            return

        def handle(result: str | None) -> None:
            if result == "hide":
                key = repo_key(s.repo_path)
                subprocess.run([SESSIONS_INDEX, "tag", key, s.id, "archived"], capture_output=True)
                self._reload_sessions()
                self._populate_table()
            elif result == "delete":
                delete_session_from_index(s.repo_path, s.id)
                self._reload_sessions()
                self._populate_table()

        self.push_screen(ArchiveModal(s.name, s.is_ghost, s.is_orphan), handle)

    def action_resume_session(self) -> None:
        s = self._current_session()
        if not s:
            return
        # Suspend TUI, resume session, return to TUI on exit
        profile = s.profile
        resume_id = s.id
        with self.suspend():
            binary = "claude" if profile == "default" else f"claude-{profile}"
            cmd = [binary, "--resume", resume_id]
            subprocess.run(cmd)
