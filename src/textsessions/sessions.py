"""Session loading and data model for textsessions."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

_HEX_NAME_RE = re.compile(r'^[0-9a-f]{5,8}$')

import yaml

from .config import Config, RepoConfig, STATE_DIR, repo_key

CACHE_PATH = STATE_DIR / "_cache.json"

PRIORITY_ORDER = {"H0": 0, "1": 1, "2": 2, "3": 3, "": 9}


@dataclass
class Session:
    id: str
    name: str
    profile: str
    last_active: str
    slug: str
    tags: list[str] = field(default_factory=list)
    priority: str = ""
    repo_label: str = ""
    repo_path: Path = field(default_factory=Path)
    pinned: bool = False
    description: str = ""

    @property
    def priority_order(self) -> int:
        return PRIORITY_ORDER.get(self.priority, 9)

    @property
    def short_id(self) -> str:
        return self.id[:8]

    @property
    def display_priority(self) -> str:
        if not self.priority:
            return ""
        if self.priority.startswith("H"):
            return self.priority
        return f"P{self.priority}"

    @property
    def is_ghost(self) -> bool:
        """Repo directory no longer exists on disk."""
        return not (self.repo_path / ".git").exists()

    @property
    def is_orphan(self) -> bool:
        """Throwaway session: Claude auto-named with a 5-8 char hex hash, no metadata.

        Tagging a session 'keep' sets self.tags, which makes this return False —
        use `scan-ghosts --keep <prefix>` to permanently exclude a hex-named session.
        """
        if self.tags or self.priority:
            return False
        return bool(_HEX_NAME_RE.match(self.name))

    @property
    def is_archived(self) -> bool:
        return "archived" in self.tags

    @property
    def is_automated(self) -> bool:
        """Session created by an automated runner (pp worker, CI, etc.)."""
        return "worker" in self.tags or "automated" in self.tags


def _load_yaml_index(yaml_path: Path) -> dict:
    if not yaml_path.exists():
        return {}
    with open(yaml_path) as f:
        return yaml.safe_load(f) or {}


def _sessions_from_index(yaml_path: Path, repo_label: str, repo_path: Path) -> list[Session]:
    index = _load_yaml_index(yaml_path)
    sessions = []
    for sid, entry in index.items():
        sessions.append(Session(
            id=sid,
            name=entry.get("name", sid[:8]),
            profile=entry.get("profile", ""),
            last_active=entry.get("last_active", ""),
            slug=entry.get("slug", ""),
            tags=entry.get("tags", []),
            priority=entry.get("priority", ""),
            repo_label=repo_label,
            repo_path=repo_path,
            pinned=bool(entry.get("pinned", False)),
            description=entry.get("description", ""),
        ))
    return sessions


def _expand_recursive(repo: RepoConfig) -> list[RepoConfig]:
    """Walk a recursive repo entry and return one RepoConfig per git repo found."""
    expanded = []
    for candidate in sorted(repo.path.iterdir()):
        if candidate.is_dir() and (candidate / ".git").exists():
            expanded.append(RepoConfig(
                path=candidate,
                label=f"{repo.label}/{candidate.name}",
                profile=repo.profile,
                recursive=False,
            ))
    return expanded


def _sort_sessions(sessions: list[Session], by_priority: bool = False) -> list[Session]:
    """Sort sessions pinned-first, then by last_active desc (or priority+last_active asc)."""
    if by_priority:
        key = lambda s: (s.priority_order, s.last_active)
        reverse = False
    else:
        key = lambda s: s.last_active
        reverse = True
    pinned = sorted([s for s in sessions if s.pinned], key=key, reverse=reverse)
    rest = sorted([s for s in sessions if not s.pinned], key=key, reverse=reverse)
    return pinned + rest


def load_sessions(config: Config, show_archived: bool = False) -> list[Session]:
    """Load all sessions from all configured repos, sorted by last_active desc."""
    all_sessions: list[Session] = []

    repos_to_load: list[RepoConfig] = []
    for repo in config.repos:
        if repo.recursive:
            repos_to_load.extend(_expand_recursive(repo))
        else:
            repos_to_load.append(repo)

    for repo in repos_to_load:
        key = repo_key(repo.path)
        yaml_path = STATE_DIR / f"{key}.yaml"
        sessions = _sessions_from_index(yaml_path, repo.label, repo.path)
        all_sessions.extend(sessions)

    all_sessions = _sort_sessions(all_sessions)
    if not show_archived:
        all_sessions = [s for s in all_sessions if not s.is_archived]
    return all_sessions


def _cache_is_fresh() -> bool:
    """True if _cache.json exists and its mtime >= every *.yaml in STATE_DIR."""
    if not CACHE_PATH.exists():
        return False
    cache_mtime = os.path.getmtime(CACHE_PATH)
    for yaml_path in STATE_DIR.glob("*.yaml"):
        if os.path.getmtime(yaml_path) > cache_mtime:
            return False
    return True


def _write_cache(sessions: list[Session]) -> None:
    """Serialise sessions to JSON cache (resume-relevant fields only)."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    data = [
        {
            "id": s.id,
            "name": s.name,
            "profile": s.profile,
            "repo_label": s.repo_label,
            "repo_path": str(s.repo_path),
        }
        for s in sessions
    ]
    with open(CACHE_PATH, "w") as f:
        json.dump(data, f)


def _load_cache() -> list[Session]:
    """Deserialise Session objects from JSON cache."""
    with open(CACHE_PATH) as f:
        data = json.load(f)
    sessions = []
    for d in data:
        sessions.append(Session(
            id=d["id"],
            name=d["name"],
            profile=d["profile"],
            last_active="",
            slug="",
            repo_label=d["repo_label"],
            repo_path=Path(d["repo_path"]),
        ))
    return sessions


def load_sessions_fast(config: Config) -> list[Session]:
    """Load sessions, using flat JSON cache if fresh. Falls back to load_sessions."""
    if _cache_is_fresh():
        return _load_cache()
    sessions = load_sessions(config)
    _write_cache(sessions)
    return sessions


def filter_sessions(
    sessions: list[Session],
    query: str = "",
    tag: str = "",
    profile: str = "",
    repo_label: str = "",
    show_archived: bool = False,
    show_automated: bool = False,
    ghosts_only: bool = False,
) -> list[Session]:
    result = sessions
    if not show_archived:
        result = [s for s in result if not s.is_archived]
    # Hide automated sessions unless explicitly requested via tag filter
    automated_tags = {"worker", "automated"}
    explicitly_requesting_automated = tag in automated_tags or (
        query and any(w[1:] in automated_tags for w in query.lower().split() if w.startswith("#"))
    )
    if not show_automated and not explicitly_requesting_automated:
        result = [s for s in result if not s.is_automated]
    if ghosts_only:
        result = [s for s in result if s.is_ghost or s.is_orphan]
    if query:
        words = query.lower().split()
        tag_filters = [w[1:] for w in words if w.startswith("#") and len(w) > 1]
        text_words = [w for w in words if not w.startswith("#")]
        for t in tag_filters:
            result = [s for s in result if t in s.tags]
        if text_words:
            q = " ".join(text_words)
            result = [s for s in result if q in s.slug.lower() or q in s.name.lower() or q in s.description.lower()]
    if tag:
        result = [s for s in result if tag in s.tags]
    if profile:
        result = [s for s in result if s.profile == profile]
    if repo_label:
        result = [s for s in result if s.repo_label == repo_label or s.repo_label.startswith(repo_label + "/")]
    return result


def delete_session_from_index(repo_path: Path, session_id: str) -> bool:
    """Remove a session entry directly from the YAML index. Returns True if removed."""
    key = repo_key(repo_path)
    yaml_path = STATE_DIR / f"{key}.yaml"
    if not yaml_path.exists():
        return False
    with open(yaml_path) as f:
        index = yaml.safe_load(f) or {}
    if session_id not in index:
        return False
    del index[session_id]
    with open(yaml_path, "w") as f:
        yaml.safe_dump(index, f, default_flow_style=False, sort_keys=False, width=120)
    return True


def sort_by_priority(sessions: list[Session]) -> list[Session]:
    return _sort_sessions(sessions, by_priority=True)
