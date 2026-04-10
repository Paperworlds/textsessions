"""CLI entrypoint for textsessions."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

import json as _json

from . import __version__
from .config import CONFIG_PATH, RepoConfig, load, repo_key, run_init, save
from .proxy import fmt_tokens, load_all_time, load_current_session
from .sessions import CACHE_PATH, delete_session_from_index, filter_sessions, load_sessions, load_sessions_fast, sort_by_priority


@click.group(invoke_without_command=True)
@click.version_option(__version__, "--version", "-V")
@click.pass_context
def main(ctx: click.Context) -> None:
    """textsessions — TUI for Claude Code session management."""
    if ctx.invoked_subcommand is None:
        # Default: launch TUI
        config = load()
        if not config.repos:
            click.echo("No repos configured. Run: textsessions init")
            return
        from .tui.app import TextSessionsApp
        app = TextSessionsApp(config)
        app.run()


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
    from rich.console import Console
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
def scan() -> None:
    """Re-scan and update config (non-interactive)."""
    run_init(interactive=False)


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



# ---------------------------------------------------------------------------
# Profile subcommand group
# ---------------------------------------------------------------------------

@main.group("profile")
def profile_group() -> None:
    """Manage cloak profiles and integration status."""


@profile_group.command("status")
def profile_status() -> None:
    """Show integration status (cloak, ai-proxy)."""
    from .profiles import (
        aiproxy_available,
        aiproxy_running,
        cloak_available,
        cloak_version,
        list_cloak_profiles,
    )

    console = Console()

    # Cloak
    if cloak_available():
        ver = cloak_version()
        ver_str = f" ({ver})" if ver else ""
        profiles = list_cloak_profiles()
        profiles_str = f"  {len(profiles)} profiles: {', '.join(profiles)}" if profiles else "  no profiles found"
        console.print(f"Cloak:    [green]installed{ver_str}[/green]{profiles_str}")
    else:
        console.print("Cloak:    [yellow]not installed[/yellow] — run: [dim]npm install -g @synth1s/cloak[/dim]")

    # ai-proxy
    if aiproxy_available():
        if aiproxy_running():
            console.print("ai-proxy: [green]installed, running[/green] (localhost:7474)")
        else:
            console.print("ai-proxy: [yellow]installed, not running[/yellow]")
    else:
        console.print("ai-proxy: [dim]not installed[/dim]")


@profile_group.command("list")
def profile_list() -> None:
    """List cloak profiles with which repos use them."""
    from .profiles import cloak_available, list_cloak_profiles

    config = load()
    console = Console()

    cloak_profiles = list_cloak_profiles()

    # Build mapping: profile -> list of repo labels from config
    profile_repos: dict[str, list[str]] = {}
    for p in cloak_profiles:
        profile_repos[p] = []
    for repo in config.repos:
        p = repo.profile
        if p not in profile_repos:
            profile_repos[p] = []
        profile_repos[p].append(repo.label)

    if not profile_repos:
        if not cloak_available():
            console.print(
                "[yellow]Cloak is not installed.[/yellow] Profiles exist in textsessions config "
                "but won't be isolated until cloak is set up.\n"
                "Run: [dim]npm install -g @synth1s/cloak[/dim]"
            )
        else:
            console.print("[dim]No profiles found in ~/.cloak/profiles/ or config.[/dim]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Profile")
    table.add_column("Repos")
    for profile, repos in sorted(profile_repos.items()):
        repos_str = ", ".join(repos) if repos else "[dim](none configured)[/dim]"
        table.add_row(profile, repos_str)
    console.print(table)

    if not cloak_available():
        console.print(
            "\n[dim]Note: cloak not installed — profiles exist in config but won't be isolated.[/dim]\n"
            "[dim]Run: npm install -g @synth1s/cloak[/dim]"
        )


@profile_group.command("setup")
@click.argument("name")
def profile_setup(name: str) -> None:
    """Guide user through creating a cloak profile named NAME."""
    from .profiles import cloak_available, cloak_profile_dir

    console = Console()

    if not cloak_available():
        console.print("[red]Cloak is not installed.[/red]")
        console.print("Install it first:\n  [bold]npm install -g @synth1s/cloak[/bold]")
        raise SystemExit(1)

    d = cloak_profile_dir(name)
    if d is not None:
        console.print(f"[green]Profile '{name}' already exists:[/green] {d}")
        return

    console.print(f"[bold]Setting up cloak profile:[/bold] {name}\n")
    console.print("Cloak requires an interactive browser-based OAuth login.")
    console.print("Run the following command in your terminal:\n")
    console.print(f"  [bold]cloak create {name}[/bold]\n")
    console.print("After completing the login, verify with:")
    console.print(f"  [bold]textsessions profile check[/bold]")


@profile_group.command("check")
def profile_check() -> None:
    """Check that all profiles in config have a cloak profile dir."""
    from .profiles import cloak_available, cloak_profile_dir

    config = load()
    console = Console()

    used_profiles = sorted({r.profile for r in config.repos})
    if not used_profiles:
        console.print("[dim]No repos configured. Run: textsessions init[/dim]")
        return

    all_ok = True
    for profile in used_profiles:
        if profile == "default":
            console.print(f"  [dim]{profile}[/dim]  [green]ok[/green] (uses system default)")
            continue
        if not cloak_available():
            console.print(
                f"  {profile}  [yellow]cloak not installed[/yellow] — "
                f"run: [dim]npm install -g @synth1s/cloak[/dim]"
            )
            all_ok = False
            continue
        d = cloak_profile_dir(profile)
        if d:
            console.print(f"  [bold]{profile}[/bold]  [green]ok[/green]  {d}")
        else:
            console.print(
                f"  [bold]{profile}[/bold]  [red]missing[/red] — "
                f"run: [dim]textsessions profile setup {profile}[/dim]"
            )
            all_ok = False

    if all_ok:
        console.print("\n[green]All profiles OK.[/green]")
    else:
        console.print("\n[yellow]Some profiles need setup.[/yellow]")


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
def sessions_cmd(query: str, tag: str, profile: str, repo: str, use_cwd: bool, by_priority: bool, limit: int, resume_name: str, names_only: bool) -> None:
    """Print session table (non-TUI, for scripting)."""
    config = load()
    if not config.repos:
        click.echo("No repos configured. Run: textsessions init")
        return

    if use_cwd:
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
            click.echo("Run: textsessions init", err=True)
            sys.exit(1)
        repo = best.label
        # Auto-reindex so the list is always current
        from .config import detect_claude_dirs
        from .indexer import build_index
        rk = repo_key(best.path)
        pairs = [
            f"{cd}::{cd / 'projects' / rk}"
            for cd in detect_claude_dirs()
            if (cd / "projects" / rk).exists()
        ]
        if pairs:
            build_index(rk, pairs)

    all_sessions = load_sessions_fast(config) if resume_name else load_sessions(config)

    if resume_name:
        matched = [s for s in all_sessions if s.name == resume_name or s.id.startswith(resume_name) or s.name.startswith(resume_name)]
        if not matched:
            click.echo(f"No session matching '{resume_name}'", err=True)
            sys.exit(1)
        s = matched[0]
        import subprocess
        from .profiles import build_launch_env, resume_cmd
        env = build_launch_env(s.profile, {"cloak": config.integrations.cloak, "aiproxy": config.integrations.aiproxy})
        cmd = resume_cmd(s.id, s.name, s.profile, env, config.ui.claude_cmd)
        sys.exit(subprocess.run(cmd, env=env, cwd=s.repo_path).returncode)

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
    has_desc = any(s.description for s in filtered)
    table.add_column("Name" if not has_desc else "Description", style="bold")
    if has_desc:
        table.add_column("Name", style="dim")
    table.add_column("Repo")
    table.add_column("Profile")
    table.add_column("Tags")
    table.add_column("Pri")
    table.add_column("Last Active")

    for s in filtered:
        tags_str = " ".join(f"#{t}" for t in s.tags)
        pri = s.display_priority
        if has_desc:
            table.add_row(s.description or s.name, s.name if s.description else "", s.repo_label, s.profile, tags_str, pri, s.last_active)
        else:
            table.add_row(s.name, s.repo_label, s.profile, tags_str, pri, s.last_active)

    console.print(table)


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
        console.print("  [dim]No proxy data (is claude-context-proxy running?)[/dim]")

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

    # --keep: tag one session as 'keep' to permanently exclude from orphan detection
    if keep_prefix:
        if not repo_label:
            click.echo("--repo is required when using --keep", err=True)
            sys.exit(1)
        from .indexer import do_tag, load_index, save_index, write_legacy_tsv
        from .config import repo_key as _repo_key
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
        return

    # --keep-all: tag every detected orphan in the repo as 'keep'
    if do_keep_all:
        if not repo_label:
            click.echo("--repo is required when using --keep-all", err=True)
            sys.exit(1)
        from .indexer import do_tag, load_index, save_index, write_legacy_tsv
        from .config import repo_key as _repo_key
        orphans_to_keep = [s for s in all_sessions if not s.is_ghost and s.is_orphan]
        if not orphans_to_keep:
            click.echo(f"No orphans found in {repo_label}.")
            return
        by_path: dict[str, list] = {}
        for s in orphans_to_keep:
            by_path.setdefault(str(s.repo_path), []).append(s)
        kept = 0
        for repo_path_str, sessions in by_path.items():
            from pathlib import Path as _Path
            rkey = _repo_key(_Path(repo_path_str))
            index = load_index(rkey)
            for s in sessions:
                index = do_tag(index, s.id, "keep")
                kept += 1
            save_index(rkey, index)
            write_legacy_tsv(rkey, index)
        console = Console()
        console.print(f"[green]Kept {kept} orphans in {repo_label}.[/green]")
        return

    ghosts = [s for s in all_sessions if s.is_ghost]
    orphans = [s for s in all_sessions if not s.is_ghost and s.is_orphan]
    flagged = ghosts + orphans

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
        click.echo(_json.dumps(out, indent=2))
        return

    console = Console()

    by_repo: dict[str, list] = {}
    for s in flagged:
        by_repo.setdefault(s.repo_label, []).append(s)

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

    if not flagged:
        return

    if not do_archive and not do_delete and not do_discard:
        console.print("[dim]Dry run — use --archive (recommended) or --delete --yes to act.[/dim]")
        return

    if do_delete:
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
        return

    if do_archive or do_discard:
        from .indexer import do_tag, load_index, save_index, write_legacy_tsv
        from .config import repo_key as _repo_key
        archived = 0
        # Group by repo_path to batch index loads
        by_path: dict[str, list] = {}
        for s in flagged:
            by_path.setdefault(str(s.repo_path), []).append(s)
        for repo_path_str, sessions in by_path.items():
            from pathlib import Path as _Path
            rkey = _repo_key(_Path(repo_path_str))
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
    import glob
    import json as _json
    import re as _re
    from pathlib import Path
    from .config import load, repo_key
    from .indexer import do_rename, load_index, save_index, write_legacy_tsv

    _HEX = _re.compile(r"^[0-9a-f]{5,8}$")
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
                        d = _json.loads(line)
                        if d.get("type") == "custom-title":
                            custom_title = d.get("customTitle", "")
                except (OSError, _json.JSONDecodeError):
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
    import re
    import shlex
    import subprocess

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

    # Derive the command to use
    raw = ai_profile or config.ui.ai_search_profile  # e.g. "claude-personal" or "personal"
    tpl = config.ui.claude_cmd
    if "{profile}" in tpl:
        ai_cmd = tpl.format(profile=raw)
    else:
        ai_cmd = raw  # treat as full command name

    cmd = shlex.split(ai_cmd) + ["-p"]

    console = Console()
    if capped:
        console.print(f"[dim]  (searching {MAX_SESSIONS} of {len(all_sessions)} sessions)[/dim]", highlight=False)

    try:
        result = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        click.echo(f"Command not found: {cmd[0]!r}. Set ui.ai_search_profile in config.", err=True)
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

    data = _json.loads(m.group())
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
        click.echo(_json.dumps(out, indent=2))
        return

    table = Table(show_header=True, header_style="bold")
    has_desc = any(s.description for s in matched)
    table.add_column("Description" if has_desc else "Name", style="bold")
    if has_desc:
        table.add_column("Name", style="dim")
    table.add_column("Repo")
    table.add_column("Tags")
    table.add_column("Last Active")

    for s in matched:
        tags_str = " ".join(f"#{t}" for t in s.tags)
        if has_desc:
            table.add_row(s.description or s.name, s.name if s.description else "", s.repo_label, tags_str, s.last_active)
        else:
            table.add_row(s.name, s.repo_label, tags_str, s.last_active)

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
    import yaml
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
        text = _json.dumps(data, indent=2)
    else:
        text = yaml.dump(data, default_flow_style=False, sort_keys=False, width=120, allow_unicode=True)

    if output == "-":
        click.echo(text, nl=False)
    else:
        Path(output).write_text(text)
        click.echo(f"Written to {output}")


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
