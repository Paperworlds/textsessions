from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from textaccounts import __version__
from textaccounts.config import load_registry
from textaccounts import core

console = Console()


@click.group()
@click.version_option(__version__, prog_name="textaccounts")
def main() -> None:
    """Manage Claude config profiles."""


@main.command()
@click.argument("name")
@click.argument("path", type=click.Path())
def adopt(name: str, path: str) -> None:
    """Adopt an existing Claude config directory as a named profile."""
    registry = load_registry()
    profile = core.adopt(name, Path(path), registry)
    console.print(
        f"[green]Adopted[/green] profile [bold]{profile.name}[/bold] → {profile.path}"
    )


@main.command("create")
@click.argument("name")
@click.option("--worker", is_flag=True, help="Create a minimal worker profile.")
@click.option("--from", "parent", default=None, help="Parent profile name (required with --worker).")
def create(name: str, worker: bool, parent: str | None) -> None:
    """Create a new profile from the current config or as a worker."""
    registry = load_registry()
    if worker:
        if not parent:
            raise click.UsageError("--from <parent> is required with --worker")
        profile = core.create_worker(name, parent, registry)
        console.print(
            f"[green]Created[/green] worker profile [bold]{profile.name}[/bold]"
            f" (parent: {profile.parent})"
        )
    else:
        profile = core.create_from_current(name, registry)
        console.print(
            f"[green]Created[/green] profile [bold]{profile.name}[/bold] → {profile.path}"
        )


@main.command("list")
def list_cmd() -> None:
    """List all profiles."""
    registry = load_registry()
    profiles = core.list_profiles(registry)

    table = Table(show_header=True, header_style="bold")
    table.add_column("", width=1)
    table.add_column("Name")
    table.add_column("Path")
    table.add_column("Email")
    table.add_column("Size")
    table.add_column("Tags")

    for p in profiles:
        active_marker = "*" if p["active"] else ""
        size_kb = p["dir_size"] // 1024
        tags = "\\[worker]" if p["worker"] else ""
        table.add_row(
            active_marker,
            p["name"],
            str(p["path"]),
            p["email"] or "",
            f"{size_kb}K",
            tags,
        )

    console.print(table)


@main.command()
@click.argument("name")
def switch(name: str) -> None:
    """Switch to a profile (prints fish env line for eval)."""
    registry = load_registry()
    line = core.switch(name, registry)
    click.echo(line)


@main.command()
def status() -> None:
    """Show active profile status."""
    registry = load_registry()
    info = core.get_status(registry)

    if not info["active"]:
        console.print("[yellow]No active profile[/yellow]")
        return

    console.print(f"[bold]Active profile:[/bold] {info['active']}")
    console.print(f"[bold]Path:[/bold] {info['path']}")
    if info["email"]:
        console.print(f"[bold]Email:[/bold] {info['email']}")
    console.print(f"[bold]Sessions:[/bold] {info['sessions']}")
    if info["env_dir"]:
        sync = "[green]in sync[/green]" if info["in_sync"] else "[red]out of sync[/red]"
        console.print(f"[bold]CLAUDE_CONFIG_DIR:[/bold] {info['env_dir']} ({sync})")
    else:
        console.print("[bold]CLAUDE_CONFIG_DIR:[/bold] [dim]not set[/dim]")


@main.command()
def view() -> None:
    """Launch the interactive profile view."""
    from textaccounts.view import TextAccountsApp
    TextAccountsApp().run()
