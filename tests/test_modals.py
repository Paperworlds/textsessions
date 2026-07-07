"""Tests for TUI modals — especially Select widget edge cases."""

from __future__ import annotations

import asyncio

import pytest

from textsessions.tui.modals import PriorityModal, NewSessionModal


# ---------------------------------------------------------------------------
# PriorityModal — Select value must never be False/None/invalid
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("current_priority", [
    "",        # no priority set
    "H0",     # valid priority
    "1",      # valid priority
    "clear",  # valid clear value
    False,    # bug: YAML parsed `priority: false` as bool
    None,     # defensive
    "bogus",  # unknown value
])
def test_priority_modal_opens_without_error(current_priority):
    """PriorityModal must not crash on any priority value from the index."""

    async def _run():
        modal = PriorityModal("test-session", current_priority)
        # Mount inside a throwaway app so compose() runs
        from textual.app import App, ComposeResult
        from textual.widgets import Static

        class Host(App):
            def compose(self) -> ComposeResult:
                yield Static("host")

        app = Host()
        async with app.run_test() as pilot:
            app.push_screen(modal)
            await pilot.pause()
            # Modal should be on the screen stack without crashing
            screen_names = [type(s).__name__ for s in app.screen_stack]
            assert "PriorityModal" in screen_names

    asyncio.run(_run())


def test_new_session_modal_opens_without_error():
    """NewSessionModal priority Select must not crash."""

    async def _run():
        modal = NewSessionModal(["work", "personal"], "work", "/tmp/fake")
        from textual.app import App, ComposeResult
        from textual.widgets import Static

        class Host(App):
            def compose(self) -> ComposeResult:
                yield Static("host")

        app = Host()
        async with app.run_test() as pilot:
            app.push_screen(modal)
            await pilot.pause()
            screen_names = [type(s).__name__ for s in app.screen_stack]
            assert "NewSessionModal" in screen_names

    asyncio.run(_run())
