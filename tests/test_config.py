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

from textsessions.config import CONFIG_PATH, GitProfile, load, save, Config


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


# ---------------------------------------------------------------------------
# git_profiles round-trip
# ---------------------------------------------------------------------------

_GIT_PROFILES_TOML = b"""\
[[git_profiles]]
name = "pdonorio"
display_name = "Paolo D'Onorio De Meo"
email = "p.donorio.demeo@gmail.com"

[[git_profiles]]
name = "paolo-paradex"
display_name = "Paolo (Paradex)"
email = "paolo@paradigm.co"
signing_key = "ABCD1234"

[default_git_profiles]
work = "paolo-paradex"
personal = "pdonorio"
"""


def test_load_git_profiles(tmp_path):
    with patch("textsessions.config.CONFIG_PATH", tmp_path / "config.toml"):
        (tmp_path / "config.toml").write_bytes(_GIT_PROFILES_TOML)
        config = load()

    assert len(config.git_profiles) == 2
    gp = config.git_profiles[0]
    assert gp.name == "pdonorio"
    assert gp.display_name == "Paolo D'Onorio De Meo"
    assert gp.email == "p.donorio.demeo@gmail.com"
    assert gp.signing_key == ""

    gp2 = config.git_profiles[1]
    assert gp2.signing_key == "ABCD1234"

    assert config.default_git_profiles == {"work": "paolo-paradex", "personal": "pdonorio"}


def test_save_round_trip_git_profiles(tmp_path):
    config = Config(
        git_profiles=[
            GitProfile(name="pdonorio", display_name="Paolo", email="p@g.com"),
            GitProfile(name="work", display_name="Paolo W", email="w@p.co", signing_key="KEY1"),
        ],
        default_git_profiles={"personal": "pdonorio"},
    )
    config_path = tmp_path / "config.toml"
    with patch("textsessions.config.CONFIG_PATH", config_path):
        save(config)
        loaded = load()

    assert len(loaded.git_profiles) == 2
    assert loaded.git_profiles[0].name == "pdonorio"
    assert loaded.git_profiles[1].signing_key == "KEY1"
    assert loaded.default_git_profiles == {"personal": "pdonorio"}


def test_load_empty_git_profiles(tmp_path):
    raw = b'checkpoint_log = false\n'
    with patch("textsessions.config.CONFIG_PATH", tmp_path / "config.toml"):
        (tmp_path / "config.toml").write_bytes(raw)
        config = load()
    assert config.git_profiles == []
    assert config.default_git_profiles == {}
