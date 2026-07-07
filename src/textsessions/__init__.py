"""textsessions — Textual TUI for Claude Code session management."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("textsessions")
except PackageNotFoundError:
    __version__ = "unknown"
