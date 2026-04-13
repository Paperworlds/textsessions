"""Tests for the fast session cache used by --resume."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml


@pytest.fixture()
def fake_state_dir(tmp_path, monkeypatch):
    """Redirect STATE_DIR and CACHE_PATH to a temp directory."""
    import textsessions.sessions as sess_mod
    import textsessions.config as config_mod

    monkeypatch.setattr(sess_mod, "STATE_DIR", tmp_path)
    monkeypatch.setattr(sess_mod, "CACHE_PATH", tmp_path / "_cache.json")
    monkeypatch.setattr(config_mod, "STATE_DIR", tmp_path)
    return tmp_path


def _write_yaml(state_dir: Path, key: str, entries: dict) -> Path:
    path = state_dir / f"{key}.yaml"
    with open(path, "w") as f:
        yaml.safe_dump(entries, f)
    return path


def _make_config(state_dir: Path, repos: list[dict]):
    """Build a minimal Config-like object pointing at tmp repos."""
    from textsessions.config import Config, RepoConfig

    repo_objs = []
    for r in repos:
        rp = Path(r["path"])
        rp.mkdir(parents=True, exist_ok=True)
        (rp / ".git").mkdir(exist_ok=True)
        repo_objs.append(RepoConfig(path=rp, label=r["label"], profile=r.get("profile", "default")))

    cfg = Config(repos=repo_objs)
    return cfg


class TestCacheHelpers:
    def test_cache_is_fresh_no_cache(self, fake_state_dir):
        from textsessions.sessions import _cache_is_fresh
        assert _cache_is_fresh() is False

    def test_cache_is_fresh_after_write(self, fake_state_dir, tmp_path):
        from textsessions.sessions import _cache_is_fresh, _write_cache

        # Write a YAML first, then write cache (cache mtime >= yaml mtime)
        _write_yaml(fake_state_dir, "repo-a", {})
        time.sleep(0.01)
        _write_cache([])
        assert _cache_is_fresh() is True

    def test_cache_stale_after_yaml_touch(self, fake_state_dir):
        from textsessions.sessions import _cache_is_fresh, _write_cache

        _write_cache([])
        time.sleep(0.01)
        # Touch a YAML file after the cache was written
        yaml_path = _write_yaml(fake_state_dir, "repo-b", {})
        assert _cache_is_fresh() is False


class TestLoadSessionsFast:
    def test_second_call_uses_cache(self, fake_state_dir, tmp_path):
        """load_sessions_fast called twice: second call hits cache."""
        from textsessions.sessions import _cache_is_fresh, load_sessions_fast

        # Set up two YAML indexes
        repo_a = tmp_path / "repo_a"
        repo_b = tmp_path / "repo_b"
        repo_a.mkdir()
        repo_b.mkdir()
        (repo_a / ".git").mkdir()
        (repo_b / ".git").mkdir()

        from textsessions.config import repo_key as _repo_key
        key_a = _repo_key(repo_a)
        key_b = _repo_key(repo_b)
        _write_yaml(fake_state_dir, key_a, {
            "aaa111": {"name": "alpha", "profile": "default", "last_active": "2024-01-01 12:00", "slug": "alpha"},
        })
        _write_yaml(fake_state_dir, key_b, {
            "bbb222": {"name": "beta", "profile": "default", "last_active": "2024-01-02 12:00", "slug": "beta"},
        })

        cfg = _make_config(fake_state_dir, [
            {"path": str(repo_a), "label": "repo-a"},
            {"path": str(repo_b), "label": "repo-b"},
        ])

        # First call — cold, builds cache
        sessions1 = load_sessions_fast(cfg)
        assert len(sessions1) == 2
        assert _cache_is_fresh() is True

        # Second call — should serve from cache
        sessions2 = load_sessions_fast(cfg)
        names = {s.name for s in sessions2}
        assert names == {"alpha", "beta"}

    def test_cache_includes_last_active(self, fake_state_dir, tmp_path):
        """Cache entries must include last_active from the YAML index."""
        from textsessions.sessions import load_sessions_fast

        repo = tmp_path / "repo_c"
        repo.mkdir()
        (repo / ".git").mkdir()

        from textsessions.config import repo_key as _repo_key
        key = _repo_key(repo)
        _write_yaml(fake_state_dir, key, {
            "ccc333": {"name": "gamma", "profile": "work", "last_active": "2026-04-13 19:13", "slug": "gamma"},
        })

        cfg = _make_config(fake_state_dir, [{"path": str(repo), "label": "repo-c", "profile": "work"}])
        sessions = load_sessions_fast(cfg)
        assert len(sessions) == 1
        assert sessions[0].last_active == "2026-04-13 19:13"

        # Verify it round-trips through the cache
        sessions2 = load_sessions_fast(cfg)
        assert sessions2[0].last_active == "2026-04-13 19:13"

    def test_cache_invalidated_by_yaml_touch(self, fake_state_dir, tmp_path):
        """After touching a YAML, _cache_is_fresh() returns False."""
        from textsessions.sessions import _cache_is_fresh, _write_cache

        _write_cache([])
        time.sleep(0.01)
        _write_yaml(fake_state_dir, "some-repo", {})
        assert _cache_is_fresh() is False
