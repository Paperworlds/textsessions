"""CLI entrypoint for textsessions."""

from __future__ import annotations

import glob
import json
import re
import shlex
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

import click
from rich.console import Console
from rich.table import Table

from . import __version__
from .config import CONFIG_PATH, RepoConfig, load, repo_key, run_init, save
from .proxy import fmt_tokens, load_all_time, load_current_session
from .sessions import CACHE_PATH, delete_session_from_index, filter_sessions, load_sessions, load_sessions_fast, sort_by_priority

try:
    _git_hash = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=Path(__file__).parent,
        stderr=subprocess.DEVNULL,
        text=True,
    ).strip()
    _version_str = f"{__version__} ({_git_hash})"
except Exception:
    _version_str = __version__


def _resolve_repo_from_cwd(config, *, add_hint: str = "Run: textsessions add .") -> RepoConfig:
    """Return the deepest configured repo whose path contains CWD, or exit."""
    cwd = Path.cwd()
    best: RepoConfig | None = None
    best_len = -1
    for r in config.repos:
        try:
            cwd.relative_to(r.path)
        except ValueError:
            continue
        parts = len(r.path.parts)
        if parts > best_len:
            best_len = parts
            best = r
    if best is None:
        click.echo(f"No configured repo matches current directory ({cwd}).", err=True)
        click.echo(add_hint, err=True)
        sys.exit(1)
    if best.path != cwd and (cwd / ".git").exists():
        click.echo(f"Note: '{cwd.name}' is not configured — matched parent '{best.label}'. Run: textsessions add .", err=True)
    return best


@click.group()
@click.version_option(_version_str, "--version", "-V", prog_name="textsessions")
def main() -> None:
    """textsessions — TUI for Claude Code session management."""


@main.command()
@click.option("--config", "config_mode", is_flag=True, help="Open repo config view")
def view(config_mode: bool) -> None:
    """Launch the interactive TUI."""
    config = load()
    if config_mode:
        from .tui.config_screen import ConfigApp
        ConfigApp(config).run()
        return
    if not config.repos:
        click.echo("No repos configured. Run: textsessions init")
        return
    from .tui.app import TextSessionsApp
    TextSessionsApp(config).run()


def _complete_repo_labels(ctx: click.Context, param: click.Parameter, incomplete: str) -> list[click.shell_completion.CompletionItem]:
    try:
        config = load()
        return [
            click.shell_completion.CompletionItem(r.label, help=str(r.path))
            for r in config.repos
            if incomplete.lower() in r.label.lower()
        ]
    except Exception:
        return []


def _complete_profiles(ctx: click.Context, param: click.Parameter, incomplete: str) -> list[click.shell_completion.CompletionItem]:
    try:
        from .profiles import _HAS_TEXTACCOUNTS, list_textaccounts_profiles
        if _HAS_TEXTACCOUNTS:
            return [
                click.shell_completion.CompletionItem(p)
                for p in list_textaccounts_profiles()
                if incomplete.lower() in p.lower()
            ]
    except Exception:
        pass
    return []


@main.command("new")
@click.option("--repo", "-r", "repo_label", default="",
              shell_complete=_complete_repo_labels,
              help="Repo label (default: detect from current directory).")
@click.option("--profile", "-p", default="", shell_complete=_complete_profiles,
              help="Claude profile (default: repo's configured profile).")
@click.option("--name", "-n", default="", help="Session name passed to claude --name.")
@click.option("--priority", type=click.Choice(["H0", "1", "2", "3"]), default=None,
              help="Priority to assign after launch.")
@click.option("--model", "-m", default="", help="Model to pass to claude --model.")
def new_cmd(repo_label: str, profile: str, name: str, priority: str | None, model: str) -> None:
    """Launch a new Claude Code session in a configured repo."""

    from .config import detect_claude_dirs, repo_key as _repo_key
    from .indexer import (
        do_priority,
        find_session_created_after,
        load_index,
        reindex_repos,
        save_index,
    )
    from .profiles import build_launch_env, validate_explicit_profile

    config = load()
    if not config.repos:
        click.echo("No repos configured. Run: textsessions init", err=True)
        sys.exit(1)

    # Resolve repo: explicit label or detect from cwd
    if repo_label:
        matched_repos = [r for r in config.repos
                         if r.label == repo_label
                         or r.label.startswith(repo_label + "/")]
        if not matched_repos:
            labels = ", ".join(r.label for r in config.repos)
            click.echo(f"No repo matching '{repo_label}'. Available: {labels}", err=True)
            sys.exit(1)
        repo = matched_repos[0]
    else:
        repo = _resolve_repo_from_cwd(config, add_hint="Add it with: textsessions add .")

    # Profile: explicit → validate; empty → repo default
    explicit_profile = bool(profile)
    if not profile:
        profile = repo.profile
    if explicit_profile:
        validate_explicit_profile(profile)

    # Snapshot for post-launch metadata
    rk = _repo_key(repo.path)
    known_ids: set[str] = set(load_index(rk).keys())
    launch_time = datetime.utcnow()

    # Build env and command
    env = build_launch_env(profile, {
        "textaccounts": config.integrations.textaccounts,
        "textproxy": config.integrations.textproxy,
    })
    if "CLAUDE_CONFIG_DIR" in env:
        base_cmd = "claude"
    else:
        base_cmd = config.ui.claude_cmd.format(profile=profile or "default")
    fish_parts = [base_cmd]
    if name:
        fish_parts += ["--name", shlex.quote(name)]
    if model:
        fish_parts += ["--model", shlex.quote(model)]
    # Prepend any env vars that fish's config.fish might override (e.g. ANTHROPIC_BASE_URL).
    fish_prefix = ""
    if "ANTHROPIC_BASE_URL" in env:
        fish_prefix = f"set -x ANTHROPIC_BASE_URL {shlex.quote(env['ANTHROPIC_BASE_URL'])}; "
    cmd = ["fish", "-c", fish_prefix + " ".join(fish_parts)]

    # Launch
    result = subprocess.run(cmd, env=env, cwd=repo.path)

    # Post-launch: reindex and apply priority
    claude_dirs = detect_claude_dirs()
    reindex_repos([repo], claude_dirs)
    if priority:
        sid = find_session_created_after(rk, launch_time, known_ids)
        if sid:
            index = load_index(rk)
            if sid in index:
                index = do_priority(index, sid, priority)
                save_index(rk, index)

    sys.exit(result.returncode)


@main.command()
@click.option("--yes", "-y", is_flag=True, help="Non-interactive mode (auto-detect, no prompts)")
@click.option("--recursive", "recursive_dir", default="", metavar="PATH",
              help="Scan PATH for git repos and add them all (non-interactive).")
@click.option("--profile", "recursive_profile", default="default", show_default=True,
              help="Profile to assign when using --recursive.")
def init(yes: bool, recursive_dir: str, recursive_profile: str) -> None:
    """Interactive first-run setup: scan for Claude sessions and write config."""
    if recursive_dir:
        _init_recursive(Path(recursive_dir).expanduser(), recursive_profile)
        return
    run_init(interactive=not yes)


def _init_recursive(root: Path, profile: str) -> None:
    """Find all git repos under root and add them to config."""
    console = Console()

    if not root.exists():
        console.print(f"[red]Path does not exist: {root}[/red]")
        sys.exit(1)

    # Find git repos (directories containing .git)
    git_repos = sorted(p.parent for p in root.rglob(".git") if p.is_dir())
    if not git_repos:
        console.print(f"[yellow]No git repos found under {root}[/yellow]")
        return

    config = load()
    existing_paths = {r.path for r in config.repos}
    added = 0
    for repo_path in git_repos:
        if repo_path in existing_paths:
            console.print(f"  [dim]skip[/dim] {repo_path.name}  (already configured)")
            continue
        label = repo_path.name
        config.repos.append(RepoConfig(path=repo_path, label=label, profile=profile))
        console.print(f"  [green]+[/green] {label}  [dim]{repo_path}[/dim]")
        added += 1

    save(config)
    console.print(f"\n[green]Added {added} repos to config.[/green]")


@main.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False))
@click.option("--label", "-l", default="", help="Display name (default: directory basename)")
@click.option("--profile", "-p", default="", help="Claude profile (default: auto-detect)")
@click.option("--recursive", "-r", is_flag=True, help="Scan PATH for git repos and add all")
def add(path: str, label: str, profile: str, recursive: bool) -> None:
    """Add a repo (or directory of repos) to config."""
    from .config import detect_claude_dirs
    from .indexer import reindex_repos

    console = Console()
    repo_path = Path(path).expanduser().resolve()

    if not profile:
        try:
            from textaccounts.api import active_profile
            profile = active_profile() or "default"
        except ImportError:
            profile = "default"

    config = load()
    existing_paths = {r.path for r in config.repos}

    if recursive:
        git_repos = sorted(p.parent for p in repo_path.rglob(".git") if p.is_dir())
        if not git_repos:
            console.print(f"[yellow]No git repos found under {repo_path}[/yellow]")
            return
        new_repos = []
        for rp in git_repos:
            if rp in existing_paths:
                console.print(f"  [dim]skip[/dim] {rp.name}  (already configured)")
                continue
            rc = RepoConfig(path=rp, label=rp.name, profile=profile)
            config.repos.append(rc)
            new_repos.append(rc)
            console.print(f"  [green]+[/green] {rp.name}  [dim]{rp}[/dim]")
        if not new_repos:
            console.print("[dim]Nothing new to add.[/dim]")
            return
        save(config)
        claude_dirs = detect_claude_dirs()
        total = reindex_repos(new_repos, claude_dirs)
        console.print(f"\n[green]Added {len(new_repos)} repos ({total} sessions indexed).[/green]")
    else:
        if repo_path in existing_paths:
            console.print(f"[yellow]Already configured:[/yellow] {repo_path}")
            return
        repo_label = label or repo_path.name
        rc = RepoConfig(path=repo_path, label=repo_label, profile=profile)
        config.repos.append(rc)
        save(config)
        claude_dirs = detect_claude_dirs()
        total = reindex_repos([rc], claude_dirs)
        console.print(f"[green]Added[/green] {repo_label} [dim]({total} sessions)[/dim]")


@main.command()
@click.option("--repo", "-r", "repo_label", default="", help="Limit to one repo label")
def reindex(repo_label: str) -> None:
    """Rebuild session indexes from .jsonl files for configured repos."""
    from .config import detect_claude_dirs
    from .indexer import reindex_repos
    config = load()
    if not config.repos:
        click.echo("No repos configured. Run: textsessions init")
        return
    repos = config.repos
    if repo_label:
        repos = [r for r in repos if r.label == repo_label or r.label.startswith(repo_label + "/")]
        if not repos:
            click.echo(f"No repo matching '{repo_label}'", err=True)
            sys.exit(1)
    claude_dirs = detect_claude_dirs()
    total = reindex_repos(list(repos), claude_dirs)
    if CACHE_PATH.exists():
        CACHE_PATH.unlink()
    click.echo(f"Done. {total} sessions indexed across {len(repos)} repos.")



def _complete_session_names(ctx: click.Context, param: click.Parameter, incomplete: str) -> list[click.shell_completion.CompletionItem]:
    try:
        config = load()
        sessions = load_sessions(config)
        return [
            click.shell_completion.CompletionItem(s.name, help=s.repo_label)
            for s in sessions
            if incomplete.lower() in s.name.lower()
        ]
    except Exception:
        return []


@main.command("sessions")
@click.option("--filter", "-f", "query", default="", help="Filter by name/slug")
@click.option("--tag", "-t", default="", help="Filter by tag")
@click.option("--profile", "-p", default="", help="Filter by profile")
@click.option("--repo", "-r", default="", help="Filter by repo label")
@click.option("--current-folder", "use_cwd", is_flag=True, help="Filter to the repo matching the current directory")
@click.option("--priority", "by_priority", is_flag=True, help="Sort by priority")
@click.option("--limit", "-l", default=20, show_default=True, help="Max sessions to show")
@click.option("--resume", "resume_name", default="", metavar="NAME",
              shell_complete=_complete_session_names,
              help="Resume a session by name or ID prefix.")
@click.option("--names-only", "names_only", is_flag=True, hidden=True,
              help="Print session names one per line (for shell completion).")
@click.option("--reindex", is_flag=True, help="Rebuild indexes from .jsonl before listing")
def sessions_cmd(query: str, tag: str, profile: str, repo: str, use_cwd: bool, by_priority: bool, limit: int, resume_name: str, names_only: bool, reindex: bool) -> None:
    """Print session table (non-TUI, for scripting)."""
    config = load()
    if not config.repos:
        click.echo("No repos configured. Run: textsessions init")
        return

    if use_cwd:
        best = _resolve_repo_from_cwd(config)
        repo = best.label
        # Auto-reindex the matched repo so the list is always current
        from .config import detect_claude_dirs
        from .indexer import reindex_repos
        reindex_repos([best], detect_claude_dirs(), all_repos=config.repos)
    elif reindex:
        from .config import detect_claude_dirs
        from .indexer import reindex_repos
        reindex_repos(list(config.repos), detect_claude_dirs())

    all_sessions = load_sessions_fast(config) if resume_name else load_sessions(config)

    if resume_name:
        matched = [s for s in all_sessions if s.name == resume_name or s.id.startswith(resume_name) or s.name.startswith(resume_name)]
        if not matched:
            click.echo(f"No session matching '{resume_name}'", err=True)
            sys.exit(1)
        s = matched[0]
        cwd = s.repo_path
        if not cwd.exists():
            click.echo(
                f"Error: repo path no longer exists: {cwd}\n"
                f"  Session '{s.name}' belongs to repo '{s.repo_label}'.\n"
                f"  If the folder moved, update it with:\n"
                f"    textsessions repo move {s.repo_label} /new/path",
                err=True,
            )
            sys.exit(1)
        from .profiles import build_launch_env, resume_cmd
        env = build_launch_env(s.profile, {"textaccounts": config.integrations.textaccounts, "textproxy": config.integrations.textproxy})
        cmd = resume_cmd(s.id, s.name, s.profile, env, config.ui.claude_cmd)
        sys.exit(subprocess.run(cmd, env=env, cwd=cwd).returncode)

    filtered = filter_sessions(all_sessions, query=query, tag=tag, profile=profile, repo_label=repo)
    if by_priority:
        filtered = sort_by_priority(filtered)
    filtered = filtered[:limit]

    if names_only:
        for s in filtered:
            click.echo(s.name)
        return

    console = Console()
    table = Table(show_header=True, header_style="bold")
    table.add_column("Name", style="bold")
    table.add_column("ID", style="dim")
    table.add_column("Info", style="dim")
    table.add_column("Repo")
    table.add_column("Profile")
    table.add_column("Tags")
    table.add_column("Pri")
    table.add_column("Last Active")

    for s in filtered:
        tags_str = " ".join(f"#{t}" for t in s.tags)
        pri = s.display_priority
        info = s.description or s.slug
        table.add_row(s.name, s.id[:8], info, s.repo_label, s.profile, tags_str, pri, s.last_active)

    console.print(table)


def _resolve_session_by_name(name: str, config):
    """Find a session by name/prefix across all repos. Exits if not found."""
    sessions = load_sessions(config)
    matched = [s for s in sessions if s.name == name or s.id.startswith(name) or s.name.startswith(name)]
    if not matched:
        click.echo(f"No session matching '{name}'", err=True)
        sys.exit(1)
    return matched[0]


@main.command("rename")
@click.argument("name", shell_complete=_complete_session_names)
@click.argument("new_title", nargs=-1, required=True)
def rename_cmd(name: str, new_title: tuple[str, ...]) -> None:
    """Rename a session by name."""
    from .config import repo_key as _repo_key
    from .indexer import do_rename, mutate_index
    title = " ".join(new_title)
    config = load()
    s = _resolve_session_by_name(name, config)
    rk = _repo_key(s.repo_path)
    result: dict = {}
    def _rename(index, sid):
        do_rename(index, sid, title, repo_key=rk)
        result["name"] = index[sid]["name"]
    mutate_index(rk, s.id, _rename)
    click.echo(f"  {s.id[:8]}  → {result['name']}  [{title}]")


@main.command("tag")
@click.argument("name", shell_complete=_complete_session_names)
@click.argument("tags_csv")
def tag_cmd(name: str, tags_csv: str) -> None:
    """Add or remove tags on a session (prefix with - to remove, e.g. auth,-old)."""
    from .config import repo_key as _repo_key
    from .indexer import do_tag, do_untag, mutate_index
    config = load()
    s = _resolve_session_by_name(name, config)
    rk = _repo_key(s.repo_path)
    parts = [t.strip() for t in tags_csv.split(",") if t.strip()]
    to_add = [t for t in parts if not t.startswith("-")]
    to_remove = [t[1:] for t in parts if t.startswith("-")]
    result: dict = {}
    def apply(index, sid):
        if to_add:
            do_tag(index, sid, ",".join(to_add))
        if to_remove:
            do_untag(index, sid, ",".join(to_remove))
        result["tags"] = index[sid].get("tags", [])
    mutate_index(rk, s.id, apply)
    remaining = result["tags"]
    click.echo(f"  {s.id[:8]}  tags: {', '.join(remaining) if remaining else '(none)'}")


@main.command()
def proxy() -> None:
    """Show token proxy stats."""
    config = load()
    console = Console()

    current = load_current_session(config.proxy)
    all_time = load_all_time(config.proxy)

    console.print("\n[bold]Current session[/bold]")
    if current.is_live:
        console.print(f"  Input:    [green]{fmt_tokens(current.input_tokens)}[/green]")
        console.print(f"  Output:   [green]{fmt_tokens(current.output_tokens)}[/green]")
        console.print(f"  Requests: [green]{current.requests}[/green]")
        console.print(f"  Cost:     [green]${current.cost_usd:.4f}[/green]")
    else:
        console.print("  [dim]No proxy data — run `textsessions doctor` to diagnose[/dim]")

    console.print("\n[bold]All-time totals[/bold]")
    console.print(f"  Input:    {fmt_tokens(all_time.total_input_tokens)}")
    console.print(f"  Output:   {fmt_tokens(all_time.total_output_tokens)}")
    console.print(f"  Requests: {all_time.total_requests}")
    console.print(f"  Est. cost: ${all_time.estimated_cost_usd:.2f}")

    if all_time.by_model:
        console.print("\n[bold]By model[/bold]")
        for model, stats in sorted(all_time.by_model.items(), key=lambda x: -x[1]["requests"]):
            console.print(f"  [dim]{model}[/dim]  {fmt_tokens(stats['input'])} in / {fmt_tokens(stats['output'])} out  ({stats['requests']} req)")

    console.print()


def _scan_ghosts_keep(all_sessions: list, keep_prefix: str, repo_label: str) -> None:
    """--keep mode: tag one session as 'keep' to permanently exclude from orphan detection."""
    from .indexer import do_tag, load_index, save_index, write_legacy_tsv
    from .config import repo_key as _repo_key
    if not repo_label:
        click.echo("--repo is required when using --keep", err=True)
        sys.exit(1)
    matched = [s for s in all_sessions if s.id.startswith(keep_prefix)]
    if not matched:
        matched = [s for s in all_sessions if s.name.startswith(keep_prefix)]
    if not matched:
        click.echo(f"No session matching '{keep_prefix}'", err=True)
        sys.exit(1)
    s = matched[0]
    rkey = _repo_key(s.repo_path)
    index = load_index(rkey)
    index = do_tag(index, s.id, "keep")
    save_index(rkey, index)
    write_legacy_tsv(rkey, index)
    console = Console()
    console.print(f"Kept: {s.short_id}  {s.slug[:40]!r}")


def _scan_ghosts_keep_all(all_sessions: list, repo_label: str) -> None:
    """--keep-all mode: tag every detected orphan in the repo as 'keep'."""
    from .indexer import do_tag, load_index, save_index, write_legacy_tsv
    from .config import repo_key as _repo_key
    if not repo_label:
        click.echo("--repo is required when using --keep-all", err=True)
        sys.exit(1)
    orphans_to_keep = [s for s in all_sessions if not s.is_ghost and s.is_orphan]
    if not orphans_to_keep:
        click.echo(f"No orphans found in {repo_label}.")
        return
    by_path: dict[str, list] = {}
    for s in orphans_to_keep:
        by_path.setdefault(str(s.repo_path), []).append(s)
    kept = 0
    for repo_path_str, sessions in by_path.items():
        rkey = _repo_key(Path(repo_path_str))
        index = load_index(rkey)
        for s in sessions:
            index = do_tag(index, s.id, "keep")
            kept += 1
        save_index(rkey, index)
        write_legacy_tsv(rkey, index)
    console = Console()
    console.print(f"[green]Kept {kept} orphans in {repo_label}.[/green]")


def _scan_ghosts_report(flagged: list, by_repo: dict, as_json: bool, console: "Console") -> None:  # type: ignore[name-defined]
    """Dry-run report: print a summary of ghosts and orphans."""
    ghosts = [s for s in flagged if s.is_ghost]
    orphans = [s for s in flagged if not s.is_ghost]
    if as_json:
        out = [
            {
                "id": s.id,
                "name": s.name,
                "repo": s.repo_label,
                "kind": "ghost" if s.is_ghost else "orphan",
                "last_active": s.last_active,
                "slug": s.slug,
            }
            for s in flagged
        ]
        click.echo(json.dumps(out, indent=2))
        return
    total_ghosts = len(ghosts)
    total_orphans = len(orphans)
    for label, sessions in sorted(by_repo.items()):
        r_ghosts = sum(1 for s in sessions if s.is_ghost)
        r_orphans = sum(1 for s in sessions if not s.is_ghost)
        console.print(f"\n[bold]{label}[/bold]  [dim]({r_ghosts} ghosts, {r_orphans} orphans)[/dim]")
        for s in sessions[:20]:
            kind = "[red]ghost [/red]" if s.is_ghost else "[yellow]orphan[/yellow]"
            console.print(f"  [{kind}]  [dim]{s.id[:8]}[/dim]  {s.last_active}  {s.slug[:60]!r}")
        if len(sessions) > 20:
            console.print(f"  [dim]... {len(sessions) - 20} more[/dim]")
    console.print(f"\n[bold]Total:[/bold] {total_ghosts} ghosts, {total_orphans} orphans across {len(by_repo)} repos\n")


def _scan_ghosts_delete(flagged: list, yes: bool, console: "Console") -> None:  # type: ignore[name-defined]
    """--delete mode: hard-remove sessions from YAML index."""
    if not yes:
        click.confirm(
            f"Permanently delete {len(flagged)} sessions? This cannot be undone.\n"
            "  Tip: --archive is reversible and recommended instead.",
            abort=True,
        )
    deleted = 0
    for s in flagged:
        if delete_session_from_index(s.repo_path, s.id):
            deleted += 1
    console.print(f"[green]Deleted {deleted} sessions.[/green]")


def _scan_ghosts_archive(flagged: list, repo_label: str, do_discard: bool, console: "Console") -> None:  # type: ignore[name-defined]
    """--archive/--discard mode: tag sessions as 'archived'."""
    from .indexer import do_tag, load_index, save_index, write_legacy_tsv
    from .config import repo_key as _repo_key
    archived = 0
    # Group by repo_path to batch index loads
    by_path: dict[str, list] = {}
    for s in flagged:
        by_path.setdefault(str(s.repo_path), []).append(s)
    for repo_path_str, sessions in by_path.items():
        rkey = _repo_key(Path(repo_path_str))
        index = load_index(rkey)
        for s in sessions:
            if s.id in index and "archived" not in index[s.id].get("tags", []):
                index = do_tag(index, s.id, "archived")
                archived += 1
        save_index(rkey, index)
        write_legacy_tsv(rkey, index)
    if do_discard and repo_label:
        console.print(f"[green]Archived {archived} orphans in {repo_label}.[/green]")
    else:
        console.print(f"[green]Archived {archived} sessions.[/green]")


@main.command("scan-ghosts")
@click.option("--repo", "-r", "repo_label", default="", help="Limit to one repo label")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output")
@click.option("--archive", "do_archive", is_flag=True, help="Recommended: tag ghosts/orphans as 'archived' (reversible)")
@click.option("--delete", "do_delete", is_flag=True, help="Hard-remove sessions from YAML index (irreversible). Requires --yes.")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation when --delete")
@click.option("--keep", "keep_prefix", default="", help="Tag a hex-named session as 'keep' to exclude from future orphan detection. Requires --repo.")
@click.option("--keep-all", "do_keep_all", is_flag=True, help="Tag ALL detected orphans in a repo as 'keep'. Requires --repo.")
@click.option("--discard", "do_discard", is_flag=True, help="Archive all detected orphans/ghosts in one shot (no confirmation required).")
def scan_ghosts(repo_label: str, as_json: bool, do_archive: bool, do_delete: bool, yes: bool, keep_prefix: str, do_keep_all: bool, do_discard: bool) -> None:
    """Scan for ghost (dead repo) and orphan (throwaway) sessions.

    \b
    Orphans are sessions auto-named by Claude with a 5-8 char hex hash and
    no tags or priority set.
    Default (no flags): dry-run report, no mutations.
    --keep      Tag a hex-named session as 'keep' to exclude it permanently.
                Requires --repo.
    --keep-all  Tag ALL detected orphans in the repo as 'keep'. Requires --repo.
    --archive   Recommended: tag sessions as 'archived' so they disappear
                from normal view but remain recoverable.
    --discard   Archive all detected orphans/ghosts without a dry-run prompt.
    --delete    Permanent hard removal. Requires --yes. Use with care.
    """
    config = load()
    if not config.repos:
        click.echo("No repos configured. Run: textsessions init")
        return

    all_sessions = load_sessions(config, show_archived=True)
    if repo_label:
        all_sessions = [s for s in all_sessions if s.repo_label == repo_label or s.repo_label.startswith(repo_label + "/")]

    if keep_prefix:
        _scan_ghosts_keep(all_sessions, keep_prefix, repo_label)
        return

    if do_keep_all:
        _scan_ghosts_keep_all(all_sessions, repo_label)
        return

    ghosts = [s for s in all_sessions if s.is_ghost]
    orphans = [s for s in all_sessions if not s.is_ghost and s.is_orphan]
    flagged = ghosts + orphans

    by_repo: dict[str, list] = {}
    for s in flagged:
        by_repo.setdefault(s.repo_label, []).append(s)

    console = Console()
    _scan_ghosts_report(flagged, by_repo, as_json, console)

    if as_json or not flagged:
        return

    if not do_archive and not do_delete and not do_discard:
        console.print("[dim]Dry run — use --archive (recommended) or --delete --yes to act.[/dim]")
        return

    if do_delete:
        _scan_ghosts_delete(flagged, yes, console)
        return

    if do_archive or do_discard:
        _scan_ghosts_archive(flagged, repo_label, do_discard, console)


@main.command()
def config() -> None:
    """Show current config path and contents."""
    console = Console()
    console.print(f"Config: [dim]{CONFIG_PATH}[/dim]\n")
    cfg = load()
    if not cfg.repos:
        console.print("[yellow]No repos configured. Run: textsessions init[/yellow]")
        return
    for r in cfg.repos:
        rec = " [dim](recursive)[/dim]" if r.recursive else ""
        console.print(f"  [bold]{r.label}[/bold]  {r.path}  profile={r.profile}{rec}")
    console.print(f"\n  Proxy cache: [dim]{cfg.proxy.cache_dir}[/dim]")


# ---------------------------------------------------------------------------
# Index subcommand group
# ---------------------------------------------------------------------------

@main.group("index")
def index_group() -> None:
    """Build and mutate session YAML indexes."""


@index_group.command("build")
@click.argument("repo_key_arg", metavar="REPO-KEY")
@click.argument("pairs", nargs=-1, required=True, metavar="DIR::PATH [DIR::PATH ...]")
def index_build(repo_key_arg: str, pairs: tuple[str, ...]) -> None:
    """Rebuild the YAML index from .jsonl files.

    REPO-KEY is the repo identifier (e.g. -Users-projects-myrepo).
    Each DIR::PATH pair is <claude_dir>::<sessions_dir>.
    """
    from .indexer import build_index
    index = build_index(repo_key_arg, list(pairs))
    click.echo(f"  Built index for {repo_key_arg}: {len(index)} sessions")


@index_group.command("tag")
@click.argument("repo_key_arg", metavar="REPO-KEY")
@click.argument("prefix")
@click.argument("tags_csv")
def index_tag(repo_key_arg: str, prefix: str, tags_csv: str) -> None:
    """Add tags to a session."""
    from .indexer import do_tag, load_index, resolve_session_id, save_index, write_legacy_tsv
    index = load_index(repo_key_arg)
    sid = resolve_session_id(index, prefix)
    index = do_tag(index, sid, tags_csv)
    save_index(repo_key_arg, index)
    write_legacy_tsv(repo_key_arg, index)
    merged = index[sid].get("tags", [])
    click.echo(f"  {sid[:8]}  tags: {', '.join(merged)}")


@index_group.command("untag")
@click.argument("repo_key_arg", metavar="REPO-KEY")
@click.argument("prefix")
@click.argument("tags_csv")
def index_untag(repo_key_arg: str, prefix: str, tags_csv: str) -> None:
    """Remove tags from a session."""
    from .indexer import do_untag, load_index, resolve_session_id, save_index, write_legacy_tsv
    index = load_index(repo_key_arg)
    sid = resolve_session_id(index, prefix)
    index = do_untag(index, sid, tags_csv)
    save_index(repo_key_arg, index)
    write_legacy_tsv(repo_key_arg, index)
    remaining = index[sid].get("tags", [])
    click.echo(f"  {sid[:8]}  tags: {', '.join(remaining) if remaining else '(none)'}")


@index_group.command("rename")
@click.argument("repo_key_arg", metavar="REPO-KEY")
@click.argument("prefix")
@click.argument("new_title", nargs=-1, required=True)
def index_rename(repo_key_arg: str, prefix: str, new_title: tuple[str, ...]) -> None:
    """Rename a session (update slug/name in the index and append custom-title to .jsonl)."""
    from .indexer import do_rename, load_index, resolve_session_id, save_index, write_legacy_tsv
    title = " ".join(new_title)
    index = load_index(repo_key_arg)
    sid = resolve_session_id(index, prefix)
    index = do_rename(index, sid, title, repo_key=repo_key_arg)
    save_index(repo_key_arg, index)
    write_legacy_tsv(repo_key_arg, index)
    click.echo(f"  {sid[:8]}  → {index[sid]['slug']}")


@index_group.command("priority")
@click.argument("repo_key_arg", metavar="REPO-KEY")
@click.argument("prefix")
@click.argument("level", default="", required=False)
def index_priority(repo_key_arg: str, prefix: str, level: str) -> None:
    """Set or show session priority (H0, 1, 2, 3, clear)."""
    from .indexer import _update_legacy_priority, do_priority, load_index, resolve_session_id, save_index
    index = load_index(repo_key_arg)
    sid = resolve_session_id(index, prefix)
    entry = index[sid]

    if not level:
        pri = entry.get("priority", "")
        badge = f"[{pri}]" if pri.startswith("H") else (f"[P{pri}]" if pri else "[no priority]")
        click.echo(f"  {sid[:8]}  {badge}  {entry['slug']}")
        return

    if level not in ("H0", "1", "2", "3", "clear"):
        click.echo(f"Invalid priority: {level} (use H0, 1, 2, 3, or clear)", err=True)
        sys.exit(1)

    index = do_priority(index, sid, level)
    _update_legacy_priority(repo_key_arg, sid, level)
    save_index(repo_key_arg, index)

    pri = entry.get("priority", "")
    if level == "clear":
        click.echo(f"  {sid[:8]}  [cleared]  {entry['slug']}")
    else:
        badge = f"[{level}]" if level.startswith("H") else f"[P{level}]"
        click.echo(f"  {sid[:8]}  {badge}  {entry['slug']}")


@index_group.command("tags")
@click.argument("repo_key_arg", metavar="REPO-KEY")
def index_tags(repo_key_arg: str) -> None:
    """List all tags in use with counts."""
    from .indexer import do_tags, load_index
    index = load_index(repo_key_arg)
    counts = do_tags(index)
    if not counts:
        click.echo("  No tags in use")
        return
    for tag, count in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
        click.echo(f"  #{tag}  ({count})")


@index_group.command("delete")
@click.argument("repo_key_arg", metavar="REPO-KEY")
@click.argument("session_id")
def index_delete(repo_key_arg: str, session_id: str) -> None:
    """Remove a session from the YAML index (permanent)."""
    from .indexer import delete_session, load_index, save_index, write_legacy_tsv
    index = load_index(repo_key_arg)
    if session_id not in index:
        click.echo(f"  Session {session_id[:8]} not found", err=True)
        sys.exit(1)
    index = delete_session(index, session_id)
    save_index(repo_key_arg, index)
    write_legacy_tsv(repo_key_arg, index)
    click.echo(f"  {session_id[:8]}  deleted")


@index_group.command("auto-rename")
@click.argument("repo_key_arg", metavar="REPO-KEY", required=False)
@click.option("--dry-run", is_flag=True, help="Preview changes without applying them")
def index_auto_rename(repo_key_arg: str | None, dry_run: bool) -> None:
    """Rename hex-ID sessions that have a custom title set via /rename.

    Scans .jsonl files for custom-title entries written by Claude's /rename
    command, and applies them to index entries whose name is still a raw hex ID.
    Omit REPO-KEY to process all configured repos. Ghost sessions are skipped.
    """
    from .config import load, repo_key
    from .indexer import do_rename, load_index, save_index, write_legacy_tsv

    _HEX = re.compile(r"^[0-9a-f]{5,8}$")
    config = load()

    if repo_key_arg:
        repos = [(r, repo_key_arg) for r in config.repos if repo_key(r.path) == repo_key_arg]
        if not repos:
            repos = [(None, repo_key_arg)]
    else:
        repos = [(r, repo_key(r.path)) for r in config.repos]

    def _find_custom_titles(rk: str) -> dict[str, str]:
        """Scan .jsonl files for custom-title entries. Returns {session_id: title}."""
        titles: dict[str, str] = {}
        for claude_dir in sorted(Path.home().glob(".claude*")):
            if claude_dir.is_symlink() or not claude_dir.is_dir():
                continue
            pattern = str(claude_dir / "projects" / rk / "*.jsonl")
            for path in glob.glob(pattern):
                sid = Path(path).stem
                custom_title = ""
                try:
                    for line in open(path):
                        d = json.loads(line)
                        if d.get("type") == "custom-title":
                            custom_title = d.get("customTitle", "")
                except (OSError, json.JSONDecodeError):
                    continue
                if custom_title:
                    titles[sid] = custom_title
        return titles

    total = 0
    for repo_cfg, rk in repos:
        index = load_index(rk)
        if not index:
            continue

        custom_titles = _find_custom_titles(rk)
        to_rename = []
        for sid, entry in index.items():
            name = entry.get("name", "")
            if not _HEX.match(name):
                continue
            if repo_cfg and not (repo_cfg.path / ".git").exists():
                continue  # skip ghosts
            title = custom_titles.get(sid, "")
            if not title:
                continue
            to_rename.append((sid, name, title))

        if not to_rename:
            continue

        click.echo(f"\n{rk}  ({len(to_rename)} to rename):")
        for sid, old_name, title in to_rename:
            if dry_run:
                from .indexer import make_short_name
                new_name = make_short_name(title) or sid[:5]
                click.echo(f"  {sid[:8]}  {old_name} → {new_name}  [{title[:50]}]")
            else:
                index = do_rename(index, sid, title)  # repo_key omitted: title already in .jsonl
                click.echo(f"  {sid[:8]}  → {index[sid]['name']}  [{index[sid].get('description', '')[:50]}]")

        if not dry_run:
            save_index(rk, index)
            write_legacy_tsv(rk, index)
        total += len(to_rename)

    action = "would be" if dry_run else "were"
    click.echo(f"\n  {total} session(s) {action} renamed." + (" Run without --dry-run to apply." if dry_run and total else ""))


# ---------------------------------------------------------------------------
# AI search command
# ---------------------------------------------------------------------------

@main.command("search")
@click.argument("query")
@click.option("--profile", "ai_profile", default="", metavar="CMD", help="Override AI command/profile from config")
@click.option("--repo", "repo_label", default="", metavar="LABEL", help="Limit search to a repo")
@click.option("--limit", default=10, show_default=True, metavar="N", help="Max results")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def search_cmd(query: str, ai_profile: str, repo_label: str, limit: int, as_json: bool) -> None:
    """Search past sessions using natural language (powered by Claude).

    Sends session metadata to Claude and asks it to find relevant sessions.
    The Claude command used is configured via ui.ai_search_profile (default: claude-personal).
    """
    config = load()

    all_sessions = load_sessions(config)
    if repo_label:
        all_sessions = filter_sessions(all_sessions, repo_label=repo_label)

    if not all_sessions:
        click.echo("No sessions to search.")
        return

    # Cap to keep prompt size reasonable
    MAX_SESSIONS = 500
    capped = len(all_sessions) > MAX_SESSIONS
    sessions_to_search = all_sessions[:MAX_SESSIONS]

    # Build compact session lines for the prompt
    prompt_lines = []
    for s in sessions_to_search:
        label = s.description or s.slug
        tags = f" [{','.join(s.tags)}]" if s.tags else ""
        prompt_lines.append(f"{s.short_id}  {s.repo_label}/{s.name}  {label[:100]}{tags}")

    prompt = (
        f"Search Claude Code session history for: {query}\n\n"
        f"Sessions (short_id  repo/name  description [tags]):\n"
        + "\n".join(prompt_lines)
        + f'\n\nReply with ONLY valid JSON: {{"matches": ["id1", "id2", ...], "reason": "brief explanation"}}\n'
        f"List the short_ids of relevant sessions, most relevant first, at most {limit}.\n"
        f'If nothing matches, return {{"matches": [], "reason": "no relevant sessions found"}}.'
    )

    # ai_search_profile is a fish function/command — must run via fish -c so fish functions resolve
    ai_cmd = ai_profile or config.ui.ai_search_profile
    cmd = ["fish", "-c", f"{ai_cmd} -p"]

    console = Console()
    if capped:
        console.print(f"[dim]  (searching {MAX_SESSIONS} of {len(all_sessions)} sessions)[/dim]", highlight=False)

    try:
        result = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        click.echo("fish not found — required to resolve fish functions.", err=True)
        sys.exit(1)
    except subprocess.TimeoutExpired:
        click.echo("Search timed out.", err=True)
        sys.exit(1)

    if result.returncode != 0:
        click.echo(f"Search failed:\n{result.stderr or result.stdout}", err=True)
        sys.exit(1)

    # Extract JSON from the response (Claude may wrap it in prose)
    output = result.stdout.strip()
    m = re.search(r'\{.*?"matches".*?\}', output, re.DOTALL)
    if not m:
        click.echo(f"Could not parse response:\n{output}", err=True)
        sys.exit(1)

    data = json.loads(m.group())
    matched_ids: list[str] = data.get("matches", [])
    reason: str = data.get("reason", "")

    sid_map = {s.short_id: s for s in sessions_to_search}
    matched = [sid_map[sid] for sid in matched_ids if sid in sid_map]

    if reason:
        console.print(f"[dim]{reason}[/dim]\n", highlight=False)

    if not matched:
        click.echo("No matching sessions found.")
        return

    if as_json:
        out = [{"id": s.id, "name": s.name, "description": s.description or s.slug, "repo": s.repo_label, "last_active": s.last_active} for s in matched]
        click.echo(json.dumps(out, indent=2))
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Name", style="bold")
    table.add_column("Info", style="dim")
    table.add_column("Repo")
    table.add_column("Tags")
    table.add_column("Last Active")

    for s in matched:
        tags_str = " ".join(f"#{t}" for t in s.tags)
        info = s.description or s.slug
        table.add_row(s.name, info, s.repo_label, tags_str, s.last_active)

    console.print(table)


# ---------------------------------------------------------------------------
# Tree command
# ---------------------------------------------------------------------------

@main.command("tree")
@click.option("--output", "-o", default="-", metavar="FILE", help="Output file (default: stdout)")
@click.option("--repo", "repo_label", default="", metavar="LABEL", help="Filter to a specific repo label")
@click.option("--format", "fmt", type=click.Choice(["yaml", "json"]), default="yaml", show_default=True, help="Output format")
@click.option("--include-archived", is_flag=True, help="Include archived sessions")
def tree_cmd(output: str, repo_label: str, fmt: str, include_archived: bool) -> None:
    """Dump all repos and sessions as a YAML or JSON tree."""
    from .config import load
    from .sessions import load_sessions

    config = load()
    sessions = load_sessions(config, show_archived=include_archived)

    if repo_label:
        sessions = [s for s in sessions if s.repo_label == repo_label or s.repo_label.startswith(repo_label + "/")]

    repos_tree: dict = {}
    for s in sessions:
        repo = repos_tree.setdefault(s.repo_label, {"path": str(s.repo_path), "sessions": []})
        entry: dict = {"id": s.id, "name": s.name, "slug": s.slug, "last_active": s.last_active, "profile": s.profile}
        if s.tags:
            entry["tags"] = s.tags
        if s.priority:
            entry["priority"] = s.priority
        if s.pinned:
            entry["pinned"] = True
        repo["sessions"].append(entry)

    data = {"repos": repos_tree}

    if fmt == "json":
        text = json.dumps(data, indent=2)
    else:
        text = yaml.dump(data, default_flow_style=False, sort_keys=False, width=120, allow_unicode=True)

    if output == "-":
        click.echo(text, nl=False)
    else:
        Path(output).write_text(text)
        click.echo(f"Written to {output}")


# ---------------------------------------------------------------------------
# Repos command — CLI contract for tw repo import
# ---------------------------------------------------------------------------


@main.command("repos")
def repos_cmd() -> None:
    """Print REPO lines for all known repos (used by tw repo import)."""
    config = load()
    for repo in config.repos:
        meta = f" profile={repo.profile}" if repo.profile else ""
        click.echo(f"REPO {repo.label} {repo.path}{meta}")


@main.group("repo")
def repo_group() -> None:
    """Subcommands for managing configured repos."""


@repo_group.command("move")
@click.argument("label")
@click.argument("new_path", type=click.Path())
def repo_move(label: str, new_path: str) -> None:
    """Update a repo's registered path after the folder has been moved.

    Updates the config, renames Claude project directories to the new path key,
    renames the session index, and reindexes so all session paths are correct.

    Example: textsessions repo move mcp-fleet ~/projects/mcp-fleet
    """
    from .config import STATE_DIR, detect_claude_dirs
    from .indexer import reindex_repos

    config = load()
    matches = [r for r in config.repos if r.label == label]
    if not matches:
        raise click.UsageError(f"No repo with label '{label}'. Run 'textsessions repos' to list configured repos.")
    repo = matches[0]
    dest = Path(new_path).expanduser().resolve()
    if not dest.is_dir():
        raise click.UsageError(f"Directory not found: {dest}")
    old_path = repo.path
    if old_path == dest:
        click.echo("Path unchanged.")
        return

    old_key = repo_key(old_path)
    new_key = repo_key(dest)
    console = Console()

    # 1. Rename Claude project directories across all claude config dirs
    claude_dirs = detect_claude_dirs()
    for claude_dir in claude_dirs:
        old_proj = claude_dir / "projects" / old_key
        new_proj = claude_dir / "projects" / new_key
        if old_proj.exists() and not new_proj.exists():
            try:
                old_proj.rename(new_proj)
                console.print(f"  [green]✓[/green] claude projects: {old_key} → {new_key}  [dim]({claude_dir.name})[/dim]")
            except OSError as e:
                console.print(f"  [red]✗[/red] claude projects rename failed in {claude_dir.name}: {e}")
        elif old_proj.exists() and new_proj.exists():
            console.print(f"  [yellow]![/yellow] both project dirs exist in {claude_dir.name} — skipped (merge manually if needed)")
        else:
            console.print(f"  [dim]-[/dim] no project dir for old path in {claude_dir.name} (skipped)")

    # 2. Rename the session YAML index
    old_yaml = STATE_DIR / f"{old_key}.yaml"
    new_yaml = STATE_DIR / f"{new_key}.yaml"
    if old_yaml.exists() and not new_yaml.exists():
        try:
            old_yaml.rename(new_yaml)
            console.print(f"  [green]✓[/green] session index: {old_yaml.name} → {new_yaml.name}")
        except OSError as e:
            console.print(f"  [red]✗[/red] session index rename failed: {e}")
    elif old_yaml.exists() and new_yaml.exists():
        console.print(f"  [yellow]![/yellow] session index already exists for new path — skipped")
    else:
        console.print(f"  [dim]-[/dim] no session index for old path (skipped)")

    # 3. Update config and reindex
    repo.path = dest
    save(config)
    try:
        reindex_repos([repo], claude_dirs, all_repos=config.repos)
        console.print(f"  [green]✓[/green] reindexed")
    except Exception as e:
        console.print(f"  [yellow]![/yellow] reindex failed: {e} — run: textsessions reindex --repo {label}")
    console.print(f"[green]Done[/green]  '{label}': {old_path} → {dest}")


# ---------------------------------------------------------------------------
# Doctor command
# ---------------------------------------------------------------------------

@main.command("doctor")
def doctor_cmd() -> None:
    """Check integrations, config, and profile wiring for common problems."""
    console = Console()
    ok = True

    def check(label: str, passed: bool, detail: str = "", fix: str = "") -> None:
        nonlocal ok
        if passed:
            console.print(f"  [green]✓[/green]  {label}" + (f"  [dim]{detail}[/dim]" if detail else ""))
        else:
            ok = False
            console.print(f"  [red]✗[/red]  {label}" + (f"  [dim]{detail}[/dim]" if detail else ""))
            if fix:
                console.print(f"       [yellow]→ {fix}[/yellow]")

    config = load()
    console.print()
    console.print("[bold]Config[/bold]")
    check("Config file exists", CONFIG_PATH.exists(), str(CONFIG_PATH),
          fix=f"Run: textsessions init")
    check("At least one repo configured", bool(config.repos),
          fix="Run: textsessions add /path/to/repo")

    console.print()
    console.print("[bold]Tools[/bold]")
    claude_bin = shutil.which("claude")
    check("claude on PATH", bool(claude_bin), claude_bin or "",
          fix="Install Claude Code: https://claude.ai/code")
    fish_bin = shutil.which("fish")
    check("fish on PATH", bool(fish_bin), fish_bin or "",
          fix="Install fish shell (required for resume/launch): https://fishshell.com")

    console.print()
    console.print("[bold]textaccounts[/bold]")
    try:
        from textaccounts.api import available as ta_available, env_for_profile, list_profiles
        has_ta = True
    except ImportError:
        has_ta = False
        ta_available = lambda: False  # noqa: E731
        list_profiles = lambda: []  # noqa: E731
        env_for_profile = lambda p: {}  # noqa: E731

    ta_enabled = config.integrations.textaccounts
    check("textaccounts importable", has_ta,
          fix="Reinstall: uv tool install -e '.[accounts]' --force --python 3.13")
    if has_ta:
        check("textaccounts available (profiles registered)", ta_available(),
              fix="Run: textaccounts adopt <name> <path>")
        if ta_available():
            profiles = list_profiles()
            check("profiles registered", bool(profiles), ", ".join(profiles) if profiles else "none")

    console.print()
    console.print("[bold]textproxy[/bold]")
    from .profiles import TEXTPROXY_BASE_URL, textproxy_available, textproxy_running
    tp_enabled = config.integrations.textproxy
    check("textproxy on PATH", textproxy_available(),
          fix="Install textproxy: https://github.com/paperworlds/textproxy")
    if textproxy_available():
        check(f"textproxy running on {TEXTPROXY_BASE_URL}", textproxy_running(),
              fix="Start textproxy, or set textproxy = false under [integrations] to suppress")
    if not tp_enabled:
        console.print("  [dim]  (disabled in config)[/dim]")

    console.print()
    console.print("[bold]Repo profiles[/bold]")
    profiles_in_use = {r.profile for r in config.repos}
    if has_ta and ta_available():
        registered = set(list_profiles())
        for profile in sorted(profiles_in_use):
            resolved = bool(env_for_profile(profile)) if profile in registered else False
            check(
                f"profile '{profile}' resolves via textaccounts",
                resolved,
                fix=f"Run: textaccounts adopt {profile} <path-to-config-dir>",
            )
    else:
        for profile in sorted(profiles_in_use):
            tpl = config.ui.claude_cmd
            cmd = tpl.format(profile=profile) if "{profile}" in tpl else tpl
            on_path = bool(shutil.which(cmd))
            check(f"profile '{profile}' → '{cmd}' on PATH", on_path,
                  fix=f"Define a fish function named '{cmd}' or install textaccounts")

    console.print()
    console.print("[bold]Session indexes[/bold]")
    from .config import STATE_DIR
    check("Index directory exists", STATE_DIR.exists(), str(STATE_DIR),
          fix="Run: textsessions reindex")
    if STATE_DIR.exists():
        yaml_files = list(STATE_DIR.glob("*.yaml"))
        check("At least one index file", bool(yaml_files), f"{len(yaml_files)} repo(s)")

    console.print()
    if ok:
        console.print("[green]All checks passed.[/green]\n")
    else:
        console.print("[yellow]Some checks failed — see fixes above.[/yellow]\n")


# ---------------------------------------------------------------------------
# Backwards-compat entrypoint: mirrors old claude-sessions-index CLI
# Usage: claude-sessions-index <cmd> <repo-key> [args...]
# ---------------------------------------------------------------------------

@click.command("claude-sessions-index", context_settings={"ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def sessions_index_compat(args: tuple[str, ...]) -> None:
    """Backwards-compatible wrapper: translates old claude-sessions-index CLI to textsessions index <cmd>."""
    from .indexer import (
        _update_legacy_priority,
        build_index,
        do_priority,
        do_rename,
        do_tag,
        do_tags,
        do_untag,
        load_index,
        resolve_session_id,
        save_index,
        write_legacy_tsv,
    )

    argv = list(args)
    if len(argv) < 2:
        click.echo("Usage: claude-sessions-index <command> <repo-key> [args...]", err=True)
        sys.exit(1)

    cmd = argv[0]
    rkey = argv[1]
    rest = argv[2:]

    if cmd == "list":
        limit = 10
        filter_str = ""
        tag_filter = ""
        sort_by_priority_flag = False
        pairs: list[str] = []
        i = 0
        while i < len(rest):
            arg = rest[i]
            if arg == "--limit" and i + 1 < len(rest):
                limit = int(rest[i + 1]); i += 2
            elif arg == "--filter" and i + 1 < len(rest):
                filter_str = rest[i + 1]; i += 2
            elif arg == "--tag" and i + 1 < len(rest):
                tag_filter = rest[i + 1]; i += 2
            elif arg == "--priority":
                sort_by_priority_flag = True; i += 1
            else:
                pairs.append(arg); i += 1
        index = build_index(rkey, pairs)
        PRIORITY_ORDER = {"H0": 0, "1": 1, "2": 2, "3": 3}
        display = []
        for sid, e in index.items():
            if filter_str and filter_str not in e["slug"].lower():
                continue
            if tag_filter and tag_filter not in e.get("tags", []):
                continue
            pri_val = PRIORITY_ORDER.get(e.get("priority", ""), 9)
            display.append((pri_val, e["last_active"], sid[:8], e["profile"], e["last_active"], e["slug"], sid, e.get("priority", ""), e.get("tags", [])))
        if sort_by_priority_flag:
            display.sort(key=lambda x: (x[0], x[1]))
        shown = 0
        for pri_val, _, short_id, prof, last_dt, slug, full_sid, pri_lbl, tags in display:
            if shown >= limit:
                break
            pri_badge = f"[{pri_lbl}] " if pri_lbl.startswith("H") else (f"[P{pri_lbl}] " if pri_lbl else "")
            tag_str = "  " + " ".join(f"#{t}" for t in tags) if tags else ""
            click.echo(f"  {short_id}  {pri_badge}[{prof}]  {last_dt}  {slug}{tag_str}")
            shown += 1

    elif cmd == "tag":
        if len(rest) < 2:
            click.echo("Usage: claude-sessions-index tag <repo-key> <session-prefix> <tag1,tag2>", err=True)
            sys.exit(1)
        index = load_index(rkey)
        sid = resolve_session_id(index, rest[0])
        index = do_tag(index, sid, rest[1])
        save_index(rkey, index)
        click.echo(f"  {sid[:8]}  tags: {', '.join(index[sid].get('tags', []))}")

    elif cmd == "untag":
        if len(rest) < 2:
            click.echo("Usage: claude-sessions-index untag <repo-key> <session-prefix> <tag1,tag2>", err=True)
            sys.exit(1)
        index = load_index(rkey)
        sid = resolve_session_id(index, rest[0])
        index = do_untag(index, sid, rest[1])
        save_index(rkey, index)
        remaining = index[sid].get("tags", [])
        click.echo(f"  {sid[:8]}  tags: {', '.join(remaining) if remaining else '(none)'}")

    elif cmd == "rename":
        if len(rest) < 2:
            click.echo("Usage: claude-sessions-index rename <repo-key> <session-prefix> <new title>", err=True)
            sys.exit(1)
        index = load_index(rkey)
        sid = resolve_session_id(index, rest[0])
        new_title = " ".join(rest[1:])
        index = do_rename(index, sid, new_title, repo_key=rkey)
        save_index(rkey, index)
        write_legacy_tsv(rkey, index)
        click.echo(f"  {sid[:8]}  → {index[sid]['slug']}")

    elif cmd == "tags":
        index = load_index(rkey)
        counts = do_tags(index)
        if not counts:
            click.echo("  No tags in use")
        else:
            for tag, count in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
                click.echo(f"  #{tag}  ({count})")

    elif cmd == "priority":
        if not rest:
            click.echo("Usage: claude-sessions-index priority <repo-key> <session-prefix> [H0|1|2|3|clear]", err=True)
            sys.exit(1)
        index = load_index(rkey)
        sid = resolve_session_id(index, rest[0])
        level = rest[1] if len(rest) > 1 else ""
        entry = index[sid]
        if not level:
            pri = entry.get("priority", "")
            badge = f"[{pri}]" if pri.startswith("H") else (f"[P{pri}]" if pri else "[no priority]")
            click.echo(f"  {sid[:8]}  {badge}  {entry['slug']}")
        else:
            if level not in ("H0", "1", "2", "3", "clear"):
                click.echo(f"Invalid priority: {level}", err=True)
                sys.exit(1)
            index = do_priority(index, sid, level)
            _update_legacy_priority(rkey, sid, level)
            save_index(rkey, index)
            if level == "clear":
                click.echo(f"  {sid[:8]}  [cleared]  {entry['slug']}")
            else:
                badge = f"[{level}]" if level.startswith("H") else f"[P{level}]"
                click.echo(f"  {sid[:8]}  {badge}  {entry['slug']}")

    else:
        click.echo(f"Unknown command: {cmd}", err=True)
        sys.exit(1)
