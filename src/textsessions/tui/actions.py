"""ActionsMixin — all action_* methods for TextSessionsApp."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

from ..config import repo_key
from ..indexer import (
    do_pin,
    do_priority,
    do_rename,
    do_tag,
    do_untag,
    find_session_created_after,
    load_index,
    mutate_index,
    save_index,
    _update_legacy_priority,
)
from ..profiles import build_launch_env, resume_cmd
from ..sessions import delete_session_from_index
from .modals import (
    ArchiveModal,
    HelpModal,
    NewSessionModal,
    NewSessionResult,
    PriorityModal,
    RenameModal,
    TagModal,
    _DeleteConfirmModal,
)


class ActionsMixin:
    """All action_* methods for TextSessionsApp. Mixed in via multiple inheritance."""

    def action_focus_filter(self) -> None:
        from textual.widgets import Input
        self.query_one("#filter-input", Input).focus()

    def action_clear_filter(self) -> None:
        from textual.widgets import DataTable, Input
        inp = self.query_one("#filter-input", Input)
        inp.value = ""
        self.query_one("#sessions-table", DataTable).focus()

    def action_toggle_sort(self) -> None:
        self._sort_by_priority = not self._sort_by_priority
        self._refresh_view()

    def action_toggle_ghosts(self) -> None:
        self._ghosts_only = not self._ghosts_only
        self._refresh_view()

    def action_toggle_pins(self) -> None:
        self._show_pinned = not self._show_pinned
        self._refresh_view()
        state = "visible" if self._show_pinned else "hidden"
        self.notify(f"Pinned sessions {state}", severity="information")

    def action_toggle_all(self) -> None:
        if self._repo_filter:
            self._repo_filter = ""
        else:
            self._repo_filter = self._cwd_repo_label
        self._refresh_view()

    def action_reindex(self) -> None:
        from ..config import detect_claude_dirs
        from ..indexer import reindex_repos
        from ..sessions import _expand_recursive
        repos = [
            r for r in self._config.repos
            if not self._repo_filter
            or r.label == self._repo_filter
            or r.label.startswith(self._repo_filter + "/")
        ]
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
            self.notify(f"Reindexed — {count} sessions", severity="information")
        except Exception as e:
            self.notify(f"Reindex failed: {e}", severity="error")

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

                def apply(index, sid):
                    if to_add:
                        do_tag(index, sid, ",".join(to_add))
                    if to_remove:
                        do_untag(index, sid, ",".join(to_remove))

                mutate_index(key, s.id, apply)
                self._reload_sessions()
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

                def apply(index, sid):
                    do_priority(index, sid, result)
                    _update_legacy_priority(key, sid, result)

                mutate_index(key, s.id, apply)
                self._reload_sessions()
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
                mutate_index(key, s.id, lambda index, sid: do_rename(index, sid, result, repo_key=key))
                self._reload_sessions()
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
                    mutate_index(key, s.id, lambda index, sid: do_tag(index, sid, "archived"))
                    self._reload_sessions()
                    self.notify("Archived", severity="information")
                except Exception as e:
                    self.notify(f"Archive failed: {e}", severity="error")
            elif result == "delete":
                try:
                    delete_session_from_index(s.repo_path, s.id)
                    self._reload_sessions()
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
                    self.notify("Deleted", severity="information")
                except Exception as e:
                    self.notify(f"Delete failed: {e}", severity="error")

        self.push_screen(_DeleteConfirmModal(s.name), handle)

    def action_pin_session(self) -> None:
        s = self._current_session()
        if not s:
            return
        try:
            key = repo_key(s.repo_path)
            new_pinned = not s.pinned
            mutate_index(key, s.id, lambda index, sid: do_pin(index, sid, new_pinned))
            self._reload_sessions()
            verb = "Pinned" if new_pinned else "Unpinned"
            self.notify(verb, severity="information")
        except Exception as e:
            self.notify(f"Pin failed: {e}", severity="error")

    def action_show_help(self) -> None:
        self.push_screen(HelpModal())

    def action_resume_session(self) -> None:
        s = self._current_session()
        if not s:
            return
        profile = s.profile
        resume_id = s.id
        env = build_launch_env(profile, {
            "cloak": self._config.integrations.cloak,
            "aiproxy": self._config.integrations.aiproxy,
        })
        cmd = resume_cmd(resume_id, s.name, profile, env, self._config.ui.claude_cmd)
        with self.suspend():
            result = subprocess.run(cmd, env=env, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr, cwd=s.repo_path)
        if result.returncode != 0:
            self.notify(f"Resume failed (exit {result.returncode})", severity="error")

    def action_new_session(self) -> None:
        seen: dict[str, str] = {}  # profile -> first repo path
        for repo in self._config.repos:
            if repo.profile not in seen:
                seen[repo.profile] = str(repo.path)
        profiles = list(seen.keys()) or ["default"]

        s = self._current_session()
        default_profile = s.profile if s else profiles[0]
        default_repo_path = str(s.repo_path) if s else seen.get(default_profile, "")
        if default_profile not in profiles:
            default_profile = profiles[0]

        def handle(result: NewSessionResult | None) -> None:
            if result is None:
                return
            launch_time = datetime.utcnow()
            from ..config import repo_key as _repo_key
            rk = _repo_key(Path(result.repo_path))
            known_ids: set[str] = set(load_index(rk).keys())

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
