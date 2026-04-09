"""Main Textual application for textsessions."""

from __future__ import annotations

import subprocess
import sys
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
from ..profiles import build_launch_env, cloak_available
from ..indexer import (
    do_pin,
    do_priority,
    do_rename,
    do_tag,
    do_untag,
    find_session_created_after,
    load_index,
    resolve_session_id,
    save_index,
    write_legacy_tsv,
    _update_legacy_priority,
)
from ..proxy import SessionStats, fmt_tokens, load_current_session
from ..sessions import Session, delete_session_from_index, filter_sessions, load_sessions, sort_by_priority
from .modals import ArchiveModal, HelpModal, NewSessionModal, NewSessionResult, PriorityModal, RenameModal, TagModal, _DeleteConfirmModal

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

        # Show cloak hint once when not installed and session has a non-default profile
        if s.profile != "default" and not cloak_available():
            lines += [
                "",
                "[dim]Profiles: install cloak for isolation (textsessions profile status)[/dim]",
            ]

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
        self._reload_sessions()
        matched = _repo_for_cwd(self._config)
        if matched and self._config.ui.startup_repo == "current":
            self._cwd_repo_label = matched.label
            self._repo_filter = matched.label
            self._apply_filter()
        self._populate_table()
        self.set_interval(5, self._refresh_proxy)
        self._refresh_proxy()
        self.query_one("#sessions-table", DataTable).focus()

    def _reload_sessions(self) -> None:
        self._sessions = load_sessions(self._config)
        self._apply_filter()

    def _apply_filter(self) -> None:
        q = self._filter_query
        self._filtered = filter_sessions(
            self._sessions,
            query=q,
            repo_label=self._repo_filter,
            ghosts_only=self._ghosts_only,
        )
        if not self._show_pinned:
            self._filtered = [s for s in self._filtered if not s.pinned]
        if self._sort_by_priority:
            self._filtered = sort_by_priority(self._filtered)

    def _populate_table(self) -> None:
        table = self.query_one("#sessions-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Name", "Repo", "Profile", "Tags", "Pri", "Last Active")
        for s in self._filtered:
            pri = s.display_priority
            if s.pinned:
                name_cell = f"[bold cyan]★[/bold cyan] {s.name}"
            elif s.is_ghost:
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

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.action_resume_session()

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

    def action_toggle_pins(self) -> None:
        self._show_pinned = not self._show_pinned
        self._apply_filter()
        self._populate_table()
        state = "visible" if self._show_pinned else "hidden"
        self.notify(f"Pinned sessions {state}", severity="information")

    def action_toggle_all(self) -> None:
        if self._repo_filter:
            self._repo_filter = ""
        else:
            self._repo_filter = self._cwd_repo_label
        self._apply_filter()
        self._populate_table()

    def action_reindex(self) -> None:
        from ..config import detect_claude_dirs
        from ..indexer import reindex_repos
        from ..sessions import _expand_recursive
        repos = [r for r in self._config.repos if not self._repo_filter or r.label == self._repo_filter or r.label.startswith(self._repo_filter + "/")]
        if not repos:
            self.notify("No repos to reindex", severity="warning")
            return
        expanded = []
        for r in repos:
            if r.recursive:
                expanded.extend(_expand_recursive(r))
            else:
                expanded.append(r)
        try:
            self.notify("Reindexing…", severity="information")
            claude_dirs = detect_claude_dirs()
            count = reindex_repos(expanded, claude_dirs)
            self._reload_sessions()
            self._populate_table()
            self.notify(f"Reindexed — {count} sessions", severity="information")
        except Exception as e:
            self.notify(f"Reindex failed: {e}", severity="error")

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

    def action_tag_session(self) -> None:
        s = self._current_session()
        if not s:
            return

        def handle(result: str | None) -> None:
            if not result:
                return
            try:
                key = repo_key(s.repo_path)
                parts = [t.strip() for t in result.split(",") if t.strip()]
                to_add = [t for t in parts if not t.startswith("-")]
                to_remove = [t[1:] for t in parts if t.startswith("-")]
                index = load_index(key)
                sid = resolve_session_id(index, s.id)
                if to_add:
                    index = do_tag(index, sid, ",".join(to_add))
                if to_remove:
                    index = do_untag(index, sid, ",".join(to_remove))
                save_index(key, index)
                write_legacy_tsv(key, index)
                self._reload_sessions()
                self._populate_table()
                self.notify("Tagged", severity="information")
            except Exception as e:
                self.notify(f"Tag failed: {e}", severity="error")

        self.push_screen(TagModal(s.name, s.tags), handle)

    def action_priority_session(self) -> None:
        s = self._current_session()
        if not s:
            return

        def handle(result: str | None) -> None:
            if not result:
                return
            try:
                key = repo_key(s.repo_path)
                index = load_index(key)
                sid = resolve_session_id(index, s.id)
                index = do_priority(index, sid, result)
                _update_legacy_priority(key, sid, result)
                save_index(key, index)
                self._reload_sessions()
                self._populate_table()
                self.notify("Priority set", severity="information")
            except Exception as e:
                self.notify(f"Priority failed: {e}", severity="error")

        self.push_screen(PriorityModal(s.name, s.priority), handle)

    def action_rename_session(self) -> None:
        s = self._current_session()
        if not s:
            return

        def handle(result: str | None) -> None:
            if not result:
                return
            try:
                key = repo_key(s.repo_path)
                index = load_index(key)
                sid = resolve_session_id(index, s.id)
                index = do_rename(index, sid, result, repo_key=key)
                save_index(key, index)
                write_legacy_tsv(key, index)
                self._reload_sessions()
                self._populate_table()
                self.notify("Renamed", severity="information")
            except Exception as e:
                self.notify(f"Rename failed: {e}", severity="error")

        self.push_screen(RenameModal(s.name, s.slug), handle)

    def action_archive_session(self) -> None:
        s = self._current_session()
        if not s:
            return

        def handle(result: str | None) -> None:
            if result == "archive":
                try:
                    key = repo_key(s.repo_path)
                    index = load_index(key)
                    sid = resolve_session_id(index, s.id)
                    index = do_tag(index, sid, "archived")
                    save_index(key, index)
                    write_legacy_tsv(key, index)
                    self._reload_sessions()
                    self._populate_table()
                    self.notify("Archived", severity="information")
                except Exception as e:
                    self.notify(f"Archive failed: {e}", severity="error")
            elif result == "delete":
                try:
                    delete_session_from_index(s.repo_path, s.id)
                    self._reload_sessions()
                    self._populate_table()
                    self.notify("Deleted", severity="information")
                except Exception as e:
                    self.notify(f"Delete failed: {e}", severity="error")

        self.push_screen(ArchiveModal(s.name, s.is_ghost, s.is_orphan), handle)

    def action_delete_session_direct(self) -> None:
        """D — hard delete with a short inline confirm (no modal)."""
        s = self._current_session()
        if not s:
            return

        def handle(confirmed: bool) -> None:
            if confirmed:
                try:
                    delete_session_from_index(s.repo_path, s.id)
                    self._reload_sessions()
                    self._populate_table()
                    self.notify("Deleted", severity="information")
                except Exception as e:
                    self.notify(f"Delete failed: {e}", severity="error")

        self.push_screen(
            _DeleteConfirmModal(s.name),
            handle,
        )

    def action_pin_session(self) -> None:
        s = self._current_session()
        if not s:
            return
        try:
            key = repo_key(s.repo_path)
            index = load_index(key)
            sid = resolve_session_id(index, s.id)
            index = do_pin(index, sid, not s.pinned)
            save_index(key, index)
            write_legacy_tsv(key, index)
            self._reload_sessions()
            self._populate_table()
            verb = "Pinned" if not s.pinned else "Unpinned"
            self.notify(verb, severity="information")
        except Exception as e:
            self.notify(f"Pin failed: {e}", severity="error")

    def action_show_help(self) -> None:
        self.push_screen(HelpModal())

    def action_resume_session(self) -> None:
        s = self._current_session()
        if not s:
            return
        # Suspend TUI, resume session, return to TUI on exit
        profile = s.profile
        resume_id = s.id
        env = build_launch_env(profile, {
            "cloak": self._config.integrations.cloak,
            "aiproxy": self._config.integrations.aiproxy,
        })
        # If cloak isn't installed and profile is non-default, invoke via fish
        # so that fish functions like claude-work are available.
        if profile and profile != "default" and "CLAUDE_CONFIG_DIR" not in env:
            cmd = ["fish", "-c", f"claude-{profile} --resume {resume_id}"]
        else:
            cmd = ["claude", "--resume", resume_id]
        with self.suspend():
            result = subprocess.run(cmd, env=env, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr)
        if result.returncode != 0:
            self.notify(f"Resume failed (exit {result.returncode})", severity="error")

    def action_new_session(self) -> None:
        # Determine available profiles (deduplicated, from configured repos)
        seen: dict[str, str] = {}  # profile -> first repo path
        for repo in self._config.repos:
            if repo.profile not in seen:
                seen[repo.profile] = str(repo.path)
        profiles = list(seen.keys()) or ["default"]

        # Default to profile/repo of the currently selected session
        s = self._current_session()
        default_profile = s.profile if s else profiles[0]
        default_repo_path = str(s.repo_path) if s else seen.get(default_profile, "")
        if default_profile not in profiles:
            default_profile = profiles[0]

        def handle(result: NewSessionResult | None) -> None:
            if result is None:
                return
            launch_time = datetime.utcnow()
            # Snapshot existing session IDs for this repo before launch
            from ..config import repo_key
            rk = repo_key(Path(result.repo_path))
            from ..indexer import load_index as _load_index
            known_ids: set[str] = set(_load_index(rk).keys())

            cmd = ["claude"]
            if result.name:
                cmd += ["--name", result.name]
            env = build_launch_env(result.profile, {
                "cloak": self._config.integrations.cloak,
                "aiproxy": self._config.integrations.aiproxy,
            })

            with self.suspend():
                proc = subprocess.run(cmd, env=env, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr)
            if proc.returncode != 0:
                self.notify(f"Launch failed (exit {proc.returncode})", severity="error")

            self._apply_post_launch_metadata(result, launch_time, known_ids)

        self.push_screen(
            NewSessionModal(profiles, default_profile, default_repo_path),
            handle,
        )

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
        self._populate_table()
