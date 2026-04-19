"""E2E tests for the TextSessionsApp TUI using Textual's Pilot."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from textual.widgets import DataTable, Input

from textsessions.config import Config, ProxyConfig, RepoConfig
from textsessions.proxy import SessionStats
from textsessions.tui.app import TextSessionsApp

from conftest import make_session


@pytest.fixture
def repo_path(tmp_path):
    p = tmp_path / "myrepo"
    p.mkdir()
    return p


@pytest.fixture
def app_config(repo_path):
    return Config(
        repos=[RepoConfig(path=repo_path, label="myrepo", profile="personal")],
        proxy=ProxyConfig(cache_dir=repo_path.parent / "proxy"),
    )


@pytest.fixture
def session_list(repo_path):
    return [
        make_session(
            "a" * 32, "auth-work",
            slug="implement oauth flow",
            tags=["auth"], priority="1",
            repo_label="myrepo", repo_path=repo_path,
        ),
        make_session(
            "b" * 32, "feature-x",
            slug="add new feature x here",
            tags=[], priority="",
            repo_label="myrepo", repo_path=repo_path,
        ),
        make_session(
            "c" * 32, "bug-fix-login",
            slug="fix login regression",
            tags=["bug"], priority="2",
            repo_label="myrepo", repo_path=repo_path,
        ),
    ]


def _patched(app_config, session_list):
    """Context managers to patch data loading for all TUI tests."""
    return (
        patch("textsessions.tui.app.load_sessions", return_value=session_list),
        patch("textsessions.tui.app.load_current_session", return_value=SessionStats()),
    )


async def test_app_starts_and_shows_sessions(app_config, session_list):
    app = TextSessionsApp(config=app_config)
    p1, p2 = _patched(app_config, session_list)
    with p1, p2:
        async with app.run_test(size=(120, 40)) as pilot:
            table = pilot.app.query_one("#sessions-table", DataTable)
            assert table.row_count == 3


async def test_filter_reduces_rows(app_config, session_list):
    """Typing 'oauth' in the filter input should narrow to the one matching session."""
    app = TextSessionsApp(config=app_config)
    p1, p2 = _patched(app_config, session_list)
    with p1, p2:
        async with app.run_test(size=(120, 40)) as pilot:
            inp = pilot.app.query_one("#filter-input", Input)
            inp.value = "oauth"
            await pilot.pause()
            table = pilot.app.query_one("#sessions-table", DataTable)
            assert table.row_count == 1


async def test_filter_clear_restores_all(app_config, session_list):
    """Clearing the filter restores all sessions."""
    app = TextSessionsApp(config=app_config)
    p1, p2 = _patched(app_config, session_list)
    with p1, p2:
        async with app.run_test(size=(120, 40)) as pilot:
            inp = pilot.app.query_one("#filter-input", Input)
            inp.value = "oauth"
            await pilot.pause()
            inp.value = ""
            await pilot.pause()
            table = pilot.app.query_one("#sessions-table", DataTable)
            assert table.row_count == 3


async def test_toggle_sort_by_priority(app_config, session_list):
    """Pressing 's' toggles priority sort on and off."""
    app = TextSessionsApp(config=app_config)
    p1, p2 = _patched(app_config, session_list)
    with p1, p2:
        async with app.run_test(size=(120, 40)) as pilot:
            assert not pilot.app._sort_by_priority
            await pilot.press("s")
            assert pilot.app._sort_by_priority
            await pilot.press("s")
            assert not pilot.app._sort_by_priority


async def test_toggle_pins(app_config, session_list):
    """Pressing 'y' toggles pin visibility."""
    app = TextSessionsApp(config=app_config)
    p1, p2 = _patched(app_config, session_list)
    with p1, p2:
        async with app.run_test(size=(120, 40)) as pilot:
            assert pilot.app._show_pinned
            await pilot.press("y")
            assert not pilot.app._show_pinned
            await pilot.press("y")
            assert pilot.app._show_pinned


async def test_toggle_all_repos(app_config, session_list):
    """Pressing 'a' clears repo filter (shows all) when a repo filter is active."""
    app = TextSessionsApp(config=app_config)
    p1, p2 = _patched(app_config, session_list)
    with p1, p2:
        async with app.run_test(size=(120, 40)) as pilot:
            # Start with no filter, 'a' should set the cwd repo label (which is empty here)
            initial_filter = pilot.app._repo_filter
            await pilot.press("a")
            # Since _cwd_repo_label is "" (no matched repo), toggling sets filter to ""
            assert pilot.app._repo_filter == initial_filter


async def test_quit(app_config, session_list):
    """Pressing 'q' exits the app cleanly."""
    app = TextSessionsApp(config=app_config)
    p1, p2 = _patched(app_config, session_list)
    with p1, p2:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("q")
        assert not app.is_running


async def test_duplicate_session_id_does_not_crash(app_config, session_list, repo_path):
    """Regression: when two repos both index the same session ID (e.g. parent+child
    repo both track it), _populate_table must not raise DuplicateKey from Textual.

    Root cause: load_sessions concatenates per-repo results without deduplicating.
    A parent repo and a specifically-configured child repo can both contain the
    same session ID, causing table.add_row(key=sid) to fail.
    """
    # Inject a duplicate: same session ID, two different repo labels
    dup = make_session(
        "a" * 32, "auth-work",
        slug="implement oauth flow",
        tags=["auth"], priority="1",
        repo_label="myrepo-child",   # different label, SAME id
        repo_path=repo_path,
    )
    sessions_with_dup = session_list + [dup]

    app = TextSessionsApp(config=app_config)
    p1, p2 = _patched(app_config, sessions_with_dup)
    with p1, p2:
        async with app.run_test(size=(120, 40)) as pilot:
            table = pilot.app.query_one("#sessions-table", DataTable)
            # Should show 3 unique sessions, not crash with DuplicateKey
            assert table.row_count == 3
