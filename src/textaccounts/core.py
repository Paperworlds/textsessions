from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import click

from textaccounts.config import Profile, ProfileRegistry, extract_email, save_registry


def validate_config_dir(path: Path) -> bool:
    return (path / ".claude.json").exists()


def adopt(name: str, path: Path, registry: ProfileRegistry) -> Profile:
    path = path.expanduser().resolve()
    if name in registry.profiles:
        raise click.UsageError(f"Profile '{name}' already exists.")
    if not path.is_dir():
        raise click.UsageError(f"Directory not found: {path}")
    if not validate_config_dir(path):
        raise click.UsageError(f"Not a valid Claude config dir (missing .claude.json): {path}")

    email = extract_email(path)
    profile = Profile(
        name=name,
        path=path,
        email=email,
        adopted=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        worker=False,
        parent=None,
    )
    registry.profiles[name] = profile
    return profile


def create_from_current(name: str, registry: ProfileRegistry) -> Profile:
    if name in registry.profiles:
        raise click.UsageError(f"Profile '{name}' already exists.")

    source = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")).expanduser()
    if not validate_config_dir(source):
        raise click.UsageError(f"Current config dir is not a valid Claude config dir: {source}")

    dest = registry.profiles_dir / name
    if dest.exists():
        raise click.UsageError(f"Destination already exists: {dest}")

    shutil.copytree(source, dest)
    return adopt(name, dest, registry)


def create_worker(name: str, parent_name: str, registry: ProfileRegistry) -> Profile:
    if name in registry.profiles:
        raise click.UsageError(f"Profile '{name}' already exists.")
    if parent_name not in registry.profiles:
        raise click.UsageError(f"Parent profile '{parent_name}' not found.")

    parent = registry.profiles[parent_name]
    dest = registry.profiles_dir / name
    if dest.exists():
        raise click.UsageError(f"Destination already exists: {dest}")

    dest.mkdir(parents=True)
    for fname in (".claude.json", "settings.json"):
        src_file = parent.path / fname
        if src_file.exists():
            shutil.copy2(src_file, dest / fname)

    if not validate_config_dir(dest):
        shutil.rmtree(dest)
        raise click.UsageError(f"Parent profile is missing .claude.json: {parent.path}")

    email = extract_email(dest)
    profile = Profile(
        name=name,
        path=dest,
        email=email,
        adopted=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        worker=True,
        parent=parent_name,
    )
    registry.profiles[name] = profile
    return profile


def switch(name: str, registry: ProfileRegistry) -> str:
    if name == "default":
        return "set -e CLAUDE_CONFIG_DIR"

    if name not in registry.profiles:
        raise click.UsageError(f"Profile '{name}' not found.")

    registry.active = name
    path = registry.profiles[name].path
    return f"set -gx CLAUDE_CONFIG_DIR {path}"


def get_status(registry: ProfileRegistry) -> dict:
    env_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    active = registry.active
    profile = registry.profiles.get(active) if active else None

    in_sync = True
    if env_dir and profile:
        in_sync = Path(env_dir).resolve() == profile.path.resolve()
    elif env_dir and not profile:
        in_sync = False

    sessions = count_sessions(profile.path) if profile else 0

    return {
        "active": active,
        "path": str(profile.path) if profile else None,
        "email": profile.email if profile else None,
        "env_dir": env_dir,
        "in_sync": in_sync,
        "sessions": sessions,
    }


def count_sessions(path: Path) -> int:
    projects_dir = path / "projects"
    if not projects_dir.is_dir():
        return 0
    return sum(1 for p in projects_dir.iterdir() if p.is_dir())


def _dir_size_bytes(path: Path) -> int:
    """Return disk usage of path in bytes using du (fast, handles large dirs)."""
    import subprocess
    try:
        out = subprocess.run(
            ["du", "-sk", str(path)], capture_output=True, text=True, timeout=5
        )
        if out.returncode == 0:
            return int(out.stdout.split()[0]) * 1024
    except Exception:
        pass
    return 0


def list_profiles(registry: ProfileRegistry) -> list[dict]:
    result = []
    for name, profile in registry.profiles.items():
        size = _dir_size_bytes(profile.path) if profile.path.is_dir() else 0
        exists = profile.path.is_dir()
        result.append(
            {
                "name": name,
                "path": profile.path,
                "email": profile.email,
                "worker": profile.worker,
                "dir_size": size,
                "sessions": count_sessions(profile.path),
                "active": name == registry.active,
                "exists": exists,
            }
        )
    return result


def discover_unregistered(registry: ProfileRegistry) -> list[Path]:
    """Scan ~/.claude-*/ for valid Claude config dirs not yet registered."""
    registered = {p.path.resolve() for p in registry.profiles.values()}
    found = []
    for d in sorted(Path.home().glob(".claude*")):
        if d.is_dir() and d.resolve() not in registered and validate_config_dir(d):
            found.append(d)
    return found
