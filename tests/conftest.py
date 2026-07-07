"""Shared test helpers for textsessions tests."""

from __future__ import annotations

from pathlib import Path

from textsessions.sessions import Session


def make_session(
    sid: str = "a" * 32,
    name: str = "a1b2c",
    last_active: str = "2026-04-07 12:00",
    *,
    slug: str = "hello there",
    tags: list[str] | None = None,
    priority: str = "",
    repo_path: Path | None = None,
    repo_label: str = "test",
    profile: str = "personal",
    pinned: bool = False,
    description: str = "",
) -> Session:
    return Session(
        id=sid,
        name=name,
        profile=profile,
        last_active=last_active,
        slug=slug,
        tags=tags or [],
        priority=priority,
        repo_label=repo_label,
        repo_path=repo_path or Path("/nonexistent/path"),
        pinned=pinned,
        description=description,
    )
