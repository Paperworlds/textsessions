"""Tests for the textaccounts interactive view."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
import yaml

from textaccounts.view import TextAccountsApp, _fmt_size, _render_detail


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_profile_dir(path: Path, email: str = "test@example.com") -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / ".claude.json").write_text(
        json.dumps({"oauthAccount": {"emailAddress": email}})
    )
    return path


def _write_registry(config_path: Path, active: str | None, profiles: dict) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {"version": 1, "profiles": profiles}
    if active:
        data["active"] = active
    with config_path.open("w") as f:
        yaml.safe_dump(data, f)


# ---------------------------------------------------------------------------
# Unit tests (no Textual runtime)
# ---------------------------------------------------------------------------

def test_fmt_size_megabytes():
    assert _fmt_size(2 * 1024 * 1024) == "2M"


def test_fmt_size_kilobytes():
    assert _fmt_size(500 * 1024) == "500K"


def test_render_detail_none():
    assert "No profile selected" in _render_detail(None)


def test_render_detail_active_profile():
    p = {
        "name": "work",
        "active": True,
        "path": Path("/tmp/work"),
        "email": "pao***@example.com",
        "sessions": 12,
        "dir_size": 1024 * 512,
        "worker": False,
    }
    text = _render_detail(p)
    assert "work" in text
    assert "active" in text
    assert "12" in text
    assert "pao***@example.com" in text


def test_render_detail_worker_flag():
    p = {
        "name": "work-bot",
        "active": False,
        "path": Path("/tmp/work-bot"),
        "email": "",
        "sessions": 0,
        "dir_size": 0,
        "worker": True,
    }
    assert "worker" in _render_detail(p)


# ---------------------------------------------------------------------------
# Textual app tests
# ---------------------------------------------------------------------------

def test_view_mounts_with_profiles(tmp_path: Path):
    work = _make_profile_dir(tmp_path / "claude-work", "work@example.com")
    personal = _make_profile_dir(tmp_path / "claude-personal", "me@example.com")
    config = tmp_path / "profiles.yaml"
    _write_registry(config, "work", {
        "work": {"path": str(work)},
        "personal": {"path": str(personal)},
    })

    async def _run():
        app = TextAccountsApp(config_path=config)
        async with app.run_test() as pilot:
            table = app.query_one("DataTable")
            assert table.row_count == 2

    asyncio.run(_run())


def test_view_shows_active_marker(tmp_path: Path):
    work = _make_profile_dir(tmp_path / "claude-work")
    config = tmp_path / "profiles.yaml"
    _write_registry(config, "work", {"work": {"path": str(work)}})

    async def _run():
        app = TextAccountsApp(config_path=config)
        async with app.run_test() as pilot:
            table = app.query_one("DataTable")
            cell = table.get_cell_at((0, 0))
            assert cell == "*"

    asyncio.run(_run())


def test_switch_updates_active_marker(tmp_path: Path):
    work = _make_profile_dir(tmp_path / "claude-work")
    personal = _make_profile_dir(tmp_path / "claude-personal")
    config = tmp_path / "profiles.yaml"
    _write_registry(config, "work", {
        "work": {"path": str(work)},
        "personal": {"path": str(personal)},
    })

    async def _run():
        app = TextAccountsApp(config_path=config)
        async with app.run_test() as pilot:
            table = app.query_one("DataTable")
            await pilot.press("down")
            await pilot.press("s")
            await pilot.pause()
            assert table.get_cell_at((1, 0)) == "*"
            assert table.get_cell_at((0, 0)) == ""

    asyncio.run(_run())


def test_adopt_modal_opens_on_a(tmp_path: Path):
    config = tmp_path / "profiles.yaml"
    _write_registry(config, None, {})

    async def _run():
        from textaccounts.view import AdoptModal
        app = TextAccountsApp(config_path=config)
        async with app.run_test() as pilot:
            await pilot.press("a")
            await pilot.pause()
            assert app.screen_stack[-1].__class__ is AdoptModal

    asyncio.run(_run())


def test_adopt_registers_profile(tmp_path: Path):
    work = _make_profile_dir(tmp_path / "claude-work")
    config = tmp_path / "profiles.yaml"
    _write_registry(config, None, {})

    async def _run():
        from textual.widgets import Input
        from textaccounts.view import AdoptModal
        app = TextAccountsApp(config_path=config)
        async with app.run_test() as pilot:
            await pilot.press("a")
            await pilot.pause()
            # Query inputs from the modal screen
            modal = app.screen_stack[-1]
            modal.query_one("#name-input", Input).value = "work"
            modal.query_one("#path-input", Input).value = str(work)
            await pilot.click("#adopt-btn")
            await pilot.pause()
            table = app.query_one("DataTable")
            assert table.row_count == 1

    asyncio.run(_run())
