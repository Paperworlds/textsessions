"""Token proxy stats reader for textsessions.

Reads from textproxy cache files:
  ~/.cache/textproxy/session.json   — current session
  ~/.cache/textproxy/history.jsonl  — all-time history
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .config import ProxyConfig

# Approximate cost per 1M tokens (MTok) for claude-sonnet-4-6
# Used as fallback if no model-specific pricing available
_DEFAULT_INPUT_PRICE_PER_MTOK = 3.0
_DEFAULT_OUTPUT_PRICE_PER_MTOK = 15.0


@dataclass
class SessionStats:
    session_id: str = ""
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    is_live: bool = False  # True if proxy is running


@dataclass
class AllTimeStats:
    total_requests: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    by_model: dict[str, dict] = None

    def __post_init__(self):
        if self.by_model is None:
            self.by_model = {}


def _estimate_cost(input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens / 1_000_000 * _DEFAULT_INPUT_PRICE_PER_MTOK
        + output_tokens / 1_000_000 * _DEFAULT_OUTPUT_PRICE_PER_MTOK
    )


def load_current_session(proxy: ProxyConfig) -> SessionStats:
    """Read current session stats from session.json."""
    cache_dir = Path(str(proxy.cache_dir)).expanduser()
    session_file = cache_dir / "session.json"
    ctx_file = cache_dir / "ctx.json"

    # Try ctx.json first (has cost_usd pre-calculated)
    if ctx_file.exists():
        try:
            with open(ctx_file) as f:
                data = json.load(f)
            return SessionStats(
                session_id=data.get("session_id", ""),
                requests=data.get("requests", 0),
                input_tokens=data.get("input_tokens", 0),
                output_tokens=data.get("output_tokens", 0),
                cost_usd=data.get("cost_usd", 0.0),
                is_live=True,
            )
        except (json.JSONDecodeError, OSError):
            pass

    if not session_file.exists():
        return SessionStats()

    try:
        with open(session_file) as f:
            data = json.load(f)
        input_tok = data.get("input_tokens", 0)
        output_tok = data.get("output_tokens", 0)
        return SessionStats(
            session_id=data.get("session_id", ""),
            requests=data.get("requests", 0),
            input_tokens=input_tok,
            output_tokens=output_tok,
            cost_usd=_estimate_cost(input_tok, output_tok),
            is_live=True,
        )
    except (json.JSONDecodeError, OSError):
        return SessionStats()


def load_all_time(proxy: ProxyConfig, max_lines: int = 50_000) -> AllTimeStats:
    """Parse history.jsonl and aggregate totals + per-model breakdown."""
    cache_dir = Path(str(proxy.cache_dir)).expanduser()
    history_file = cache_dir / "history.jsonl"

    if not history_file.exists():
        return AllTimeStats()

    total_input = 0
    total_output = 0
    total_requests = 0
    by_model: dict[str, dict] = {}

    try:
        with open(history_file) as f:
            for i, line in enumerate(f):
                if i >= max_lines:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                inp = entry.get("input", 0)
                out = entry.get("output", 0)
                model = entry.get("model", "unknown") or "unknown"

                total_input += inp
                total_output += out
                total_requests += 1

                if model not in by_model:
                    by_model[model] = {"input": 0, "output": 0, "requests": 0}
                by_model[model]["input"] += inp
                by_model[model]["output"] += out
                by_model[model]["requests"] += 1
    except OSError:
        return AllTimeStats()

    return AllTimeStats(
        total_requests=total_requests,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        estimated_cost_usd=_estimate_cost(total_input, total_output),
        by_model=by_model,
    )


def fmt_tokens(n: int) -> str:
    """Format token count as human-friendly string."""
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}k"
    return str(n)
