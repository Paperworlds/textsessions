"""CLI entrypoint for textsessions."""

from __future__ import annotations

import sys

import click
from rich.console import Console
from rich.table import Table

import json as _json

from . import __version__
from .config import CONFIG_PATH, load, repo_key, run_init, save
from .proxy import fmt_tokens, load_all_time, load_current_session
from .sessions import delete_session_from_index, filter_sessions, load_sessions, sort_by_priority


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
def init(yes: bool) -> None:
    """Interactive first-run setup: scan for Claude sessions and write config."""
    run_init(interactive=not yes)


@main.command()
def scan() -> None:
    """Re-scan and update config (non-interactive)."""
    run_init(interactive=False)


@main.command("sessions")
@click.option("--filter", "-f", "query", default="", help="Filter by name/slug")
@click.option("--tag", "-t", default="", help="Filter by tag")
@click.option("--profile", "-p", default="", help="Filter by profile")
@click.option("--repo", "-r", default="", help="Filter by repo label")
@click.option("--priority", "by_priority", is_flag=True, help="Sort by priority")
@click.option("--limit", "-l", default=20, show_default=True, help="Max sessions to show")
def sessions_cmd(query: str, tag: str, profile: str, repo: str, by_priority: bool, limit: int) -> None:
    """Print session table (non-TUI, for scripting)."""
    config = load()
    if not config.repos:
        click.echo("No repos configured. Run: textsessions init")
        return

    all_sessions = load_sessions(config)
    filtered = filter_sessions(all_sessions, query=query, tag=tag, profile=profile, repo_label=repo)
    if by_priority:
        filtered = sort_by_priority(filtered)
    filtered = filtered[:limit]

    console = Console()
    table = Table(show_header=True, header_style="bold")
    table.add_column("Name", style="bold")
    table.add_column("Repo")
    table.add_column("Profile")
    table.add_column("Tags")
    table.add_column("Pri")
    table.add_column("Last Active")

    for s in filtered:
        tags_str = " ".join(f"#{t}" for t in s.tags)
        pri = s.display_priority
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
@click.option("--min-words", default=8, show_default=True, help="Orphan slug word threshold")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output")
@click.option("--archive", "do_archive", is_flag=True, help="Recommended: tag ghosts/orphans as 'archived' (reversible)")
@click.option("--delete", "do_delete", is_flag=True, help="Hard-remove sessions from YAML index (irreversible). Requires --yes.")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation when --delete")
def scan_ghosts(repo_label: str, min_words: int, as_json: bool, do_archive: bool, do_delete: bool, yes: bool) -> None:
    """Scan for ghost (dead repo) and orphan (throwaway) sessions.

    \b
    Default (no flags): dry-run report, no mutations.
    --archive   Recommended: tag sessions as 'archived' so they disappear
                from normal view but remain recoverable.
    --delete    Permanent hard removal. Requires --yes. Use with care.
    """
    config = load()
    if not config.repos:
        click.echo("No repos configured. Run: textsessions init")
        return

    all_sessions = load_sessions(config, show_archived=True)
    if repo_label:
        all_sessions = [s for s in all_sessions if s.repo_label == repo_label or s.repo_label.startswith(repo_label + "/")]

    # Override orphan threshold if custom
    from .sessions import Session as _Session

    def _is_orphan_custom(s: _Session) -> bool:
        if s.tags or s.priority:
            return False
        if len(s.name) > 8 or " " in s.name:
            return False
        return len(s.slug.split()) <= min_words

    ghosts = [s for s in all_sessions if s.is_ghost]
    orphans = [s for s in all_sessions if not s.is_ghost and _is_orphan_custom(s)]
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

    if not do_archive and not do_delete:
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

    if do_archive:
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
