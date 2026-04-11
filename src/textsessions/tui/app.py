"""Main Textual application for textsessions."""

from __future__ import annotations

from datetime import datetime
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

from ..config import Config, RepoConfig, load, repo_key
from ..profiles import textaccounts_available
from ..indexer import (
    do_priority,
    find_session_created_after,
    load_index,
    save_index,
)
from ..proxy import SessionStats, fmt_tokens, load_current_session
from ..sessions import Session, filter_sessions, load_sessions, sort_by_priority
from .actions import ActionsMixin
from .modals import NewSessionResult

PRIORITY_COLORS = {"H0": "bold red", "1": "yellow", "2": "cyan", "3": "dim", "": ""}


def _repo_for_cwd(config: Config) -> RepoConfig | None:
    """Return the closest configured repo that is a parent of (or equal to) cwd."""
    cwd = Path.cwd()
    best: RepoConfig | None = None
    best_len = -1
    for repo in config.repos:
        try:
            cwd.relative_to(repo.path)
        except ValueError:
            continue
        parts = len(repo.path.parts)
        if parts > best_len:
            best_len = parts
            best = repo
    return best


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

        detail_text = s.description or s.slug
        detail_lines = []
        while len(detail_text) > 50:
            detail_lines.append(detail_text[:50])
            detail_text = detail_text[50:]
        detail_lines.append(detail_text)
        detail_display = "\n           ".join(detail_lines)
        detail_label = "Desc:" if s.description else "Slug:"

        lines = [
            f"[bold]Name:[/bold]    [dim]{s.name}[/dim]",
            f"[bold]Repo:[/bold]    {s.repo_label}",
            f"[bold]Profile:[/bold] {s.profile}",
            f"[bold]Tags:[/bold]    {tags_str}",
            f"[bold]Priority:[/bold]{pri_str}",
            f"[bold]Active:[/bold]  {s.last_active}",
            f"[bold]ID:[/bold]      [dim]{s.id}[/dim]",
            "",
            f"[bold]{detail_label}[/bold]    [dim]{detail_display}[/dim]",
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

        # Show textaccounts hint when not configured and session has a non-default profile
        if s.profile != "default" and not textaccounts_available():
            lines += [
                "",
                "[dim]Profiles: run textaccounts adopt <name> <path> to activate isolation[/dim]",
            ]

        return "\n".join(lines)


class TextSessionsApp(ActionsMixin, App):
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
        width: 70%;
        border: solid $primary;
        padding: 0 1;
    }
    #right-panel {
        width: 30%;
        border: solid $primary-darken-2;
        padding: 1;
    }
    #filter-input {
        height: 3;
    }
    #scope-label {
        margin-bottom: 1;
        color: $text-muted;
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
        Binding("d", "archive_session", "Archive"),
        Binding("D", "delete_session_direct", "Delete"),

        Binding("x", "pin_session", "Pin"),
        Binding("y", "toggle_pins", "Pins"),
        Binding("n", "new_session", "New", show=True),
        Binding("/", "focus_filter", "Filter"),
        Binding("a", "toggle_all", "All"),
        Binding("s", "toggle_sort", "Sort"),
        Binding("g", "toggle_ghosts", "Ghosts"),
        Binding("ctrl+r", "reindex", "Reindex"),
        Binding("escape", "clear_filter", "Clear filter"),
        Binding("?", "show_help", "Help"),
        Binding("q", "quit", "Quit"),
    ]

    _sort_by_priority: reactive[bool] = reactive(False)
    _ghosts_only: reactive[bool] = reactive(False)
    _show_pinned: reactive[bool] = reactive(True)
    _filter_query: reactive[str] = reactive("")
    _repo_filter: reactive[str] = reactive("")
    _cwd_repo_label: str = ""
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
                yield Label("", id="scope-label")
                yield DataTable(id="sessions-table", cursor_type="row")
            with ScrollableContainer(id="right-panel"):
                yield SessionDetail(id="detail")
        yield Footer()

    def on_mount(self) -> None:
        self._sessions = load_sessions(self._config)
        matched = _repo_for_cwd(self._config)
        if matched and self._config.ui.startup_repo == "current":
            self._cwd_repo_label = matched.label
            self._repo_filter = matched.label
        self._refresh_view()
        self.set_interval(5, self._refresh_proxy)
        self._refresh_proxy()
        self.query_one("#sessions-table", DataTable).focus()

    def _reload_sessions(self) -> None:
        self._sessions = load_sessions(self._config)
        self._refresh_view()

    def _refresh_view(self) -> None:
        self._apply_filter()
        self._populate_table()

    def _apply_filter(self) -> None:
        q = self._filter_query
        self._filtered = filter_sessions(
            self._sessions,
            query=q,
            repo_label=self._repo_filter,
            ghosts_only=self._ghosts_only,
        )
        if self._sort_by_priority:
            self._filtered = sort_by_priority(self._filtered)
        elif not self._show_pinned:
            # Pins hidden: sort all sessions flat by last_active, ignoring pinned flag
            self._filtered = sorted(self._filtered, key=lambda s: s.last_active, reverse=True)

    def _populate_table(self) -> None:
        table = self.query_one("#sessions-table", DataTable)
        table.clear(columns=True)
        single_repo = bool(self._repo_filter)
        cols = ["Name"]
        if not single_repo:
            cols.append("Repo")
        cols += ["Profile / Tags", "Pri", "Last Active"]
        table.add_columns(*cols)
        for s in self._filtered:
            pri = s.display_priority
            label = (s.description if s.description else s.name)[:35]
            if s.pinned and self._show_pinned:
                name_cell = f"[bold cyan]★[/bold cyan] {label}"
            elif s.is_ghost:
                name_cell = f"[dim]~{label}[/dim]"
            elif s.is_orphan:
                name_cell = f"[dim]{label}[/dim]"
            else:
                name_cell = label
            tags = [t for t in s.tags if t != "archived"]
            tags_str = "  " + " ".join(f"[cyan]#{t}[/cyan]" for t in tags) if tags else ""
            profile_cell = f"{s.profile}{tags_str}"
            row = [name_cell]
            if not single_repo:
                row.append(s.repo_label[:15])
            row += [profile_cell, pri, s.last_active]
            table.add_row(*row, key=s.id)
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

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.action_resume_session()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "filter-input":
            self._filter_query = event.value
            self._refresh_view()

    def _update_scope_label(self) -> None:
        try:
            label = self.query_one("#scope-label", Label)
            repo_part = self._repo_filter or "all repos"
            pin_part = "" if self._show_pinned else "  [dim red]pins hidden[/dim red]"
            label.update(f"[dim]{repo_part}[/dim]{pin_part}")
        except NoMatches:
            pass

    def watch__repo_filter(self, value: str) -> None:
        self._update_scope_label()

    def watch__show_pinned(self, value: bool) -> None:
        self._update_scope_label()

    def _current_session(self) -> Session | None:
        table = self.query_one("#sessions-table", DataTable)
        row = table.cursor_row
        if 0 <= row < len(self._filtered):
            return self._filtered[row]
        return None

    def _apply_post_launch_metadata(
        self,
        result: NewSessionResult,
        since: datetime,
        known_ids: set[str],
    ) -> None:
        from ..config import repo_key
        self._reload_sessions()
        rk = repo_key(Path(result.repo_path))
        sid = find_session_created_after(rk, since, known_ids)
        if sid and result.priority:
            index = load_index(rk)
            if sid in index:
                index = do_priority(index, sid, result.priority)
                save_index(rk, index)
        self._reload_sessions()
