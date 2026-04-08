"""CLI entrypoint for textsessions."""

from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table

from . import __version__
from .config import CONFIG_PATH, load, run_init, save
from .proxy import fmt_tokens, load_all_time, load_current_session
from .sessions import filter_sessions, load_sessions, sort_by_priority


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
