"""Config management for textsessions.

Config file: ~/.config/textsessions/config.toml
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

import tomli_w

CONFIG_PATH = Path.home() / ".config" / "textsessions" / "config.toml"
STATE_DIR = Path.home() / ".local" / "state" / "claude-sessions"


@dataclass
class RepoConfig:
    path: Path
    label: str
    profile: str = "work"
    recursive: bool = False


@dataclass
class ProxyConfig:
    cache_dir: Path = field(default_factory=lambda: Path.home() / ".cache" / "textproxy")


@dataclass
class IntegrationsConfig:
    """Integration toggles. True means 'use if available' (auto-detected at runtime)."""
    textaccounts: bool = True  # set False to disable textaccounts even if configured
    textproxy: bool = True     # set False to disable textproxy even if running


@dataclass
class UiConfig:
    startup_repo: str = "current"       # "current" | "all"
    claude_cmd: str = "claude"          # command to run; {profile} is substituted if present
    ai_search_profile: str = "claude"  # claude command/profile used for `textsessions search`


@dataclass
class Config:
    repos: list[RepoConfig] = field(default_factory=list)
    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    integrations: IntegrationsConfig = field(default_factory=IntegrationsConfig)
    ui: UiConfig = field(default_factory=UiConfig)


def load() -> Config:
    """Load config from disk. Returns empty Config if file doesn't exist."""
    if not CONFIG_PATH.exists():
        return Config()
    with open(CONFIG_PATH, "rb") as f:
        data = tomllib.load(f)
    repos = [
        RepoConfig(
            path=Path(r["path"]),
            label=r["label"],
            profile=r.get("profile", "work"),
            recursive=r.get("recursive", False),
        )
        for r in data.get("repos", [])
    ]
    proxy_data = data.get("proxy", {})
    proxy = ProxyConfig(
        cache_dir=Path(proxy_data.get("cache_dir", str(Path.home() / ".cache" / "textproxy")))
    )
    integrations_data = data.get("integrations", {})
    integrations = IntegrationsConfig(
        textaccounts=integrations_data.get("textaccounts", True),
        textproxy=integrations_data.get("textproxy", integrations_data.get("aiproxy", True)),
    )
    ui_data = data.get("ui", {})
    ui = UiConfig(
        startup_repo=ui_data.get("startup_repo", "current"),
        claude_cmd=ui_data.get("claude_cmd", "claude"),
        ai_search_profile=ui_data.get("ai_search_profile", "claude"),
    )
    return Config(repos=repos, proxy=proxy, integrations=integrations, ui=ui)


def save(config: Config) -> None:
    """Write config to disk."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {
        "repos": [
            {k: v for k, v in {
                "path": str(r.path),
                "label": r.label,
                "profile": r.profile,
                **({"recursive": True} if r.recursive else {}),
            }.items()}
            for r in config.repos
        ],
        "proxy": {
            "cache_dir": str(config.proxy.cache_dir),
        },
        "integrations": {
            "textaccounts": config.integrations.textaccounts,
            "textproxy": config.integrations.textproxy,
        },
        "ui": {
            "startup_repo": config.ui.startup_repo,
        },
    }
    with open(CONFIG_PATH, "wb") as f:
        tomli_w.dump(data, f)


def repo_key(path: Path) -> str:
    """Derive the claude-sessions-index repo key from a path.

    e.g. /Users/projects/paradigm/mono -> -Users-projects-paradigm-mono
    """
    return str(path).replace("/", "-")


def detect_claude_dirs() -> list[Path]:
    """Find all ~/.claude-* profile directories."""
    return sorted(
        p for p in Path.home().glob(".claude*")
        if p.is_dir() and not p.is_symlink()
    )


def discover_repos_for_dir(claude_dir: Path) -> list[Path]:
    """Return repo paths that have session index YAML files."""
    projects_dir = claude_dir / "projects"
    if not projects_dir.exists():
        return []
    keys = [p.stem for p in projects_dir.iterdir() if p.is_dir()]
    # Convert repo keys back to paths
    paths = []
    for key in keys:
        candidate = Path(key.replace("-", "/", 1) if key.startswith("-") else key)
        # Normalize: leading - means leading /
        candidate = Path("/" + key[1:].replace("-", "/")) if key.startswith("-") else Path(key)
        if candidate.exists() and (candidate / ".git").exists():
            paths.append(candidate)
    return paths


def scan_repos_from_state() -> list[Path]:
    """Find all repos that have YAML session indexes in STATE_DIR."""
    if not STATE_DIR.exists():
        return []
    paths = []
    for yaml_file in STATE_DIR.glob("*.yaml"):
        key = yaml_file.stem
        # Convert key back to path: -Users-projects-foo -> /Users/projects/foo
        # Keys use - as separator but paths may have - in them.
        # The original key is made by str(path).replace("/", "-")
        # So we reverse: replace first char - with /, then remaining - only at separators.
        # Since we can't perfectly reverse, try the simple heuristic first.
        candidate = Path("/" + key[1:].replace("-", "/")) if key.startswith("-") else Path(key)
        paths.append((candidate, key))
    return paths


def run_init(interactive: bool = True) -> Config:
    """Scan for Claude sessions and build config.

    If interactive=True, prompts user for confirmation/labels.
    If interactive=False, auto-detects with default labels.
    """
    from rich.console import Console
    from rich.prompt import Confirm, Prompt

    console = Console()
    console.print("\n[bold cyan]textsessions init[/bold cyan] — scanning for Claude sessions\n")

    # Find all repo keys with session data
    found: list[tuple[Path, str, str]] = []  # (path, key, profile)
    claude_dirs = detect_claude_dirs()

    if not claude_dirs:
        console.print("[yellow]No ~/.claude-* directories found.[/yellow]")

    for claude_dir in claude_dirs:
        profile = claude_dir.name.replace(".claude-", "").replace(".claude", "default")
        projects_dir = claude_dir / "projects"
        if not projects_dir.exists():
            continue
        for repo_dir in sorted(projects_dir.iterdir()):
            if not repo_dir.is_dir():
                continue
            key = repo_dir.name
            # Convert key to path
            if key.startswith("-"):
                path = Path("/" + key[1:].replace("-", "/"))
            else:
                continue  # can't reverse reliably without leading -
            # Check if YAML index exists for this repo
            yaml_index = STATE_DIR / f"{key}.yaml"
            if yaml_index.exists() and path.exists():
                found.append((path, key, profile))

    if not found:
        console.print("[yellow]No session indexes found. Run 'jg claude sessions' first to build the index.[/yellow]")
        return Config()

    # Deduplicate paths (same path may appear in multiple profiles)
    seen_paths: dict[Path, list[str]] = {}
    for path, key, profile in found:
        if path not in seen_paths:
            seen_paths[path] = []
        if profile not in seen_paths[path]:
            seen_paths[path].append(profile)

    console.print(f"Found [bold]{len(seen_paths)}[/bold] repos with session data:\n")

    repos: list[RepoConfig] = []
    for path, profiles in sorted(seen_paths.items()):
        default_label = path.name
        profile = profiles[0]  # use first profile found

        if interactive:
            console.print(f"  [dim]{path}[/dim]  (profile: {', '.join(profiles)})")
            include = Confirm.ask(f"  Include [bold]{path.name}[/bold]?", default=True)
            if not include:
                continue
            label = Prompt.ask(f"  Label", default=default_label)
            profile = Prompt.ask(f"  Profile", default=profile, choices=profiles if len(profiles) > 1 else None)
        else:
            label = default_label
            console.print(f"  + [green]{label}[/green]  {path}  (profile: {profile})")

        repos.append(RepoConfig(path=path, label=label, profile=profile))

    # Ask about recursive dirs
    if interactive:
        console.print()
        add_recursive = Confirm.ask("Add any recursive scan dirs (e.g. ~/projects/personal)?", default=False)
        if add_recursive:
            while True:
                dir_path = Prompt.ask("  Path (empty to stop)", default="")
                if not dir_path:
                    break
                p = Path(dir_path).expanduser()
                if not p.exists():
                    console.print(f"  [yellow]{p} does not exist, skipping[/yellow]")
                    continue
                label = Prompt.ask("  Label", default=p.name)
                profile = Prompt.ask("  Profile", default="personal")
                repos.append(RepoConfig(path=p, label=label, profile=profile, recursive=True))

    config = Config(repos=repos)
    save(config)
    console.print(f"\n[green]Config written to[/green] {CONFIG_PATH}\n")
    return config
