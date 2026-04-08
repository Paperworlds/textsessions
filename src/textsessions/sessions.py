"""Session loading and data model for textsessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .config import Config, RepoConfig, STATE_DIR, repo_key

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


def load_sessions(config: Config) -> list[Session]:
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

    # Sort by last_active descending
    all_sessions.sort(key=lambda s: s.last_active, reverse=True)
    return all_sessions


def filter_sessions(
    sessions: list[Session],
    query: str = "",
    tag: str = "",
    profile: str = "",
    repo_label: str = "",
) -> list[Session]:
    result = sessions
    if query:
        q = query.lower()
        result = [s for s in result if q in s.slug.lower() or q in s.name.lower()]
    if tag:
        result = [s for s in result if tag in s.tags]
    if profile:
        result = [s for s in result if s.profile == profile]
    if repo_label:
        result = [s for s in result if s.repo_label == repo_label or s.repo_label.startswith(repo_label + "/")]
    return result


def sort_by_priority(sessions: list[Session]) -> list[Session]:
    return sorted(sessions, key=lambda s: (s.priority_order, s.last_active), reverse=False)
