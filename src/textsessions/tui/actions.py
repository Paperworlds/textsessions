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
from ..config import detect_claude_dirs
from ..profiles import build_launch_env, profile_description, resume_cmd
from ..sessions import delete_session_from_index
from .modals import (
    ArchiveModal,
    HelpModal,
    NewSessionModal,
    NewSessionResult,
    PriorityModal,
    RenameModal,
    RepoFilterModal,
    TagModal,
    _DeleteConfirmModal,
)


class ActionsMixin:
    """All action_* methods for TextSessionsApp. Mixed in via multiple inheritance."""

    def _reindex_repo_sync(self, repo_path: Path) -> None:
        """Reindex a single repo from .jsonl files (blocking)."""
        from ..indexer import reindex_repos
        matching = [r for r in self._config.repos if r.path == repo_path]
        if matching:
            reindex_repos(matching, detect_claude_dirs())

    def _reindex_repo(self, repo_path: Path) -> None:
        """Reindex a single repo in the background, then refresh the view."""
        async def _do_reindex() -> None:
            import asyncio
            await asyncio.to_thread(self._reindex_repo_sync, repo_path)
            self._reload_sessions()
        self.run_worker(_do_reindex(), exclusive=False)

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
            # Pass all_repos so reindex_repos knows the full configured set —
            # without this, a partial reindex (filtered to one repo) doesn't
            # know about sibling repos, causing parent repos to absorb child
            # repo sessions and produce duplicate session IDs across YAML files.
            count = reindex_repos(expanded, claude_dirs, all_repos=self._config.repos)
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

    def action_repo_filter(self) -> None:
        labels = [r.label for r in self._config.repos]

        def handle(result: str | None) -> None:
            if result is None:
                return
            self._repo_filter = result
            self._refresh_view()

        self.push_screen(RepoFilterModal(labels, self._repo_filter), handle)

    def action_show_help(self) -> None:
        self.push_screen(HelpModal())

    def action_resume_session(self) -> None:
        self._resume_current(no_proxy=False)

    def action_resume_session_no_proxy(self) -> None:
        """Resume direct-to-Anthropic (bypass textproxy) — needed for Remote Control."""
        self._resume_current(no_proxy=True)

    def _resume_current(self, *, no_proxy: bool) -> None:
        s = self._current_session()
        if not s:
            return
        profile = s.profile
        resume_id = s.id
        env = build_launch_env(profile, {
            "textaccounts": self._config.integrations.textaccounts,
            "textproxy": self._config.integrations.textproxy,
        }, force_no_proxy=no_proxy)
        cmd = resume_cmd(resume_id, s.name, profile, env)
        cwd = s.repo_path
        if not cwd.exists():
            self.notify(f"Repo path missing: {cwd} — use 'textsessions repo move' to fix", severity="error")
            return
        if no_proxy:
            self.notify("Resuming direct — no proxy (Remote Control enabled)", severity="information")
        with self.suspend():
            result = subprocess.run(cmd, env=env, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr, cwd=cwd)
        if result.returncode != 0:
            self.notify(f"Resume failed (exit {result.returncode})", severity="error")
        self._reindex_repo(s.repo_path)

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

            import shlex
            env = build_launch_env(result.profile, {
                "textaccounts": self._config.integrations.textaccounts,
                "textproxy": self._config.integrations.textproxy,
            })
            fish_parts = ["claude"]
            if result.name:
                fish_parts += ["--name", shlex.quote(result.name)]
            cmd = ["fish", "-c", " ".join(fish_parts)]

            with self.suspend():
                proc = subprocess.run(cmd, env=env, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr,
                                      cwd=result.repo_path)
            if proc.returncode != 0:
                self.notify(f"Launch failed (exit {proc.returncode})", severity="error")

            async def _post_launch() -> None:
                import asyncio
                await asyncio.to_thread(self._reindex_repo_sync, Path(result.repo_path))
                self._apply_post_launch_metadata(result, launch_time, known_ids)
            self.run_worker(_post_launch(), exclusive=False)

        descriptions = {p: profile_description(p) for p in profiles}
        self.push_screen(
            NewSessionModal(profiles, default_profile, default_repo_path, descriptions),
            handle,
        )

    def action_config_screen(self) -> None:
        import shutil
        import subprocess
        ts_bin = shutil.which("textsessions")
        if not ts_bin:
            self.notify("textsessions not found on PATH", severity="error")
            return
        with self.suspend():
            subprocess.run(
                [ts_bin, "view", "--config"],
                stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr,
            )
        # Reload config from disk in case it changed
        from ..config import load
        self._config = load()
        self._reload_sessions()
