"""Tests for the ConfigApp TUI (repo management)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from textsessions.config import Config, RepoConfig
from textsessions.tui.config_screen import ConfigApp, _render_detail, _short_path


# ---------------------------------------------------------------------------
# Unit tests (no Textual runtime)
# ---------------------------------------------------------------------------


def test_short_path_home_relative():
    home = Path.home()
    assert _short_path(home / "projects" / "foo") == "~/projects/foo"


def test_short_path_outside_home():
    assert _short_path(Path("/etc/hosts")) == "/etc/hosts"


def test_render_detail_none():
    text = _render_detail(None)
    assert "No repos" in text
    assert "add" in text.lower()


def test_render_detail_repo(tmp_path: Path):
    repo_dir = tmp_path / "myrepo"
    repo_dir.mkdir()
    (repo_dir / ".git").mkdir()
    repo = RepoConfig(path=repo_dir, label="myrepo", profile="work")
    text = _render_detail(repo)
    assert "myrepo" in text
    assert "work" in text


def test_render_detail_missing_path(tmp_path: Path):
    repo = RepoConfig(path=tmp_path / "gone", label="gone", profile="default")
    text = _render_detail(repo)
    assert "not found" in text


def test_render_detail_not_git(tmp_path: Path):
    nodir = tmp_path / "plain"
    nodir.mkdir()
    repo = RepoConfig(path=nodir, label="plain", profile="default")
    text = _render_detail(repo)
    assert "not a git repo" in text


def test_render_detail_recursive(tmp_path: Path):
    d = tmp_path / "parent"
    d.mkdir()
    repo = RepoConfig(path=d, label="parent", profile="work", recursive=True)
    text = _render_detail(repo)
    assert "yes" in text


# ---------------------------------------------------------------------------
# Textual app tests (pilot)
# ---------------------------------------------------------------------------


def _make_config(tmp_path: Path, count: int = 3) -> Config:
    repos = []
    for i in range(count):
        d = tmp_path / f"repo{i}"
        d.mkdir()
        (d / ".git").mkdir()
        repos.append(RepoConfig(path=d, label=f"repo{i}", profile="work"))
    return Config(repos=repos)


def test_config_app_mounts_with_repos(tmp_path: Path):
    config = _make_config(tmp_path)

    async def _run():
        app = ConfigApp(config)
        async with app.run_test():
            from textual.widgets import DataTable
            table = app.query_one("#config-table", DataTable)
            assert table.row_count == 3

    asyncio.run(_run())


def test_config_app_empty():
    config = Config(repos=[])

    async def _run():
        app = ConfigApp(config)
        async with app.run_test():
            from textual.widgets import DataTable
            table = app.query_one("#config-table", DataTable)
            assert table.row_count == 0

    asyncio.run(_run())


def test_config_app_detail_updates_on_highlight(tmp_path: Path):
    config = _make_config(tmp_path, count=2)

    async def _run():
        app = ConfigApp(config)
        async with app.run_test() as pilot:
            from textual.widgets import DataTable, Static
            # Move cursor to trigger highlight event
            await pilot.press("down")
            await pilot.press("up")
            await pilot.pause()
            table = app.query_one("#config-table", DataTable)
            assert table.row_count == 2

    asyncio.run(_run())


def test_config_app_delete_binding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config = _make_config(tmp_path, count=2)
    monkeypatch.setattr("textsessions.tui.config_screen.save", lambda c: None)

    async def _run():
        app = ConfigApp(config)
        async with app.run_test() as pilot:
            from textual.widgets import DataTable
            await pilot.press("d")
            await pilot.pause()
            # Delete modal should be on the screen stack
            screen_names = [type(s).__name__ for s in app.screen_stack]
            assert "DeleteConfirmModal" in screen_names, f"Expected delete modal, got {screen_names}"
            # Confirm by pressing the Remove button via the modal screen
            modal = app.screen_stack[-1]
            remove_btn = modal.query_one("#save")
            remove_btn.press()
            await pilot.pause()
            table = app.query_one("#config-table", DataTable)
            assert table.row_count == 1

    asyncio.run(_run())


def test_config_app_edit_label_binding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config = _make_config(tmp_path, count=1)
    monkeypatch.setattr("textsessions.tui.config_screen.save", lambda c: None)

    async def _run():
        app = ConfigApp(config)
        async with app.run_test() as pilot:
            await pilot.press("e")
            await pilot.pause()
            screen_names = [type(s).__name__ for s in app.screen_stack]
            assert "EditLabelModal" in screen_names, f"Expected label modal, got {screen_names}"

    asyncio.run(_run())


def test_config_app_edit_profile_binding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config = _make_config(tmp_path, count=1)
    monkeypatch.setattr("textsessions.tui.config_screen.save", lambda c: None)

    async def _run():
        app = ConfigApp(config)
        async with app.run_test() as pilot:
            await pilot.press("p")
            await pilot.pause()
            screen_names = [type(s).__name__ for s in app.screen_stack]
            assert "EditProfileModal" in screen_names, f"Expected profile modal, got {screen_names}"

    asyncio.run(_run())


def test_config_app_add_binding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config = Config(repos=[])
    monkeypatch.setattr("textsessions.tui.config_screen.save", lambda c: None)

    async def _run():
        app = ConfigApp(config)
        async with app.run_test() as pilot:
            await pilot.press("a")
            await pilot.pause()
            screen_names = [type(s).__name__ for s in app.screen_stack]
            assert "AddRepoModal" in screen_names, f"Expected add modal, got {screen_names}"

    asyncio.run(_run())
