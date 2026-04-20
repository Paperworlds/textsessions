"""Tests for config.py load() validation."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

import tomli_w

from textsessions.config import CONFIG_PATH, load


def _write_config(tmp_path: Path, data: bytes) -> None:
    config = tmp_path / "config.toml"
    config.write_bytes(data)


def test_load_raises_on_non_dict_repo_entry(tmp_path):
    raw = b'repos = ["not-a-dict"]\n'
    with patch("textsessions.config.CONFIG_PATH", tmp_path / "config.toml"):
        (tmp_path / "config.toml").write_bytes(raw)
        with pytest.raises(ValueError, match="mapping"):
            load()


def test_load_raises_on_missing_path_key(tmp_path):
    raw = b'[[repos]]\nlabel = "work"\n'
    with patch("textsessions.config.CONFIG_PATH", tmp_path / "config.toml"):
        (tmp_path / "config.toml").write_bytes(raw)
        with pytest.raises(ValueError, match="'path'"):
            load()


def test_load_raises_on_missing_label_key(tmp_path):
    raw = b'[[repos]]\npath = "/some/path"\n'
    with patch("textsessions.config.CONFIG_PATH", tmp_path / "config.toml"):
        (tmp_path / "config.toml").write_bytes(raw)
        with pytest.raises(ValueError, match="'label'"):
            load()


def test_load_valid_config(tmp_path):
    raw = b'[[repos]]\npath = "/some/path"\nlabel = "myrepo"\n'
    with patch("textsessions.config.CONFIG_PATH", tmp_path / "config.toml"):
        (tmp_path / "config.toml").write_bytes(raw)
        config = load()
    assert len(config.repos) == 1
    assert config.repos[0].label == "myrepo"
