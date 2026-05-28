"""
Tests for config_loader.py
All tests are pure Python — no system calls, no apt, runs on Mac and Ubuntu.
"""

import pytest
from pathlib import Path
from cloudtool.config_loader import load_config, ConfigError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write_yaml(tmp_path: Path, content: str) -> Path:
    """Write a YAML string to a temp file and return its path."""
    f = tmp_path / "test_config.yaml"
    f.write_text(content)
    return f


VALID_YAML = """
system:
  name: test-box
  ubuntu_version: "22.04"
  update_cache: true
  upgrade: false

apt_sources:
  - name: nodesource
    uri: https://deb.nodesource.com/node_20.x
    distribution: jammy
    components: [main]
    key_url: https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key
    enabled: true

packages:
  - name: curl
  - name: git
"""


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_load_valid_config(tmp_path):
    cfg = load_config(write_yaml(tmp_path, VALID_YAML))

    assert cfg.system.name == "test-box"
    assert cfg.system.ubuntu_version == "22.04"
    assert cfg.system.update_cache is True
    assert cfg.system.upgrade is False

    assert len(cfg.packages) == 2
    assert cfg.packages[0].name == "curl"
    assert cfg.packages[1].name == "git"

    assert len(cfg.apt_sources) == 1
    src = cfg.apt_sources[0]
    assert src.name == "nodesource"
    assert src.distribution == "jammy"
    assert src.components == ["main"]
    assert src.enabled is True


def test_load_config_ubuntu_2404(tmp_path):
    yaml_content = VALID_YAML.replace('"22.04"', '"24.04"')
    cfg = load_config(write_yaml(tmp_path, yaml_content))
    assert cfg.system.ubuntu_version == "24.04"


def test_empty_apt_sources_and_packages(tmp_path):
    content = """
system:
  name: minimal
  ubuntu_version: "22.04"
"""
    cfg = load_config(write_yaml(tmp_path, content))
    assert cfg.packages == []
    assert cfg.apt_sources == []


# ---------------------------------------------------------------------------
# File errors
# ---------------------------------------------------------------------------

def test_file_not_found():
    with pytest.raises(FileNotFoundError):
        load_config("/nonexistent/path/config.yaml")


def test_invalid_yaml_syntax(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text("system: {name: [unclosed")
    with pytest.raises(ConfigError, match="Failed to parse YAML"):
        load_config(f)


# ---------------------------------------------------------------------------
# system block validation
# ---------------------------------------------------------------------------

def test_missing_system_block(tmp_path):
    with pytest.raises(ConfigError, match="'system' block"):
        load_config(write_yaml(tmp_path, "packages:\n  - name: curl\n"))


def test_missing_system_name(tmp_path):
    content = """
system:
  ubuntu_version: "22.04"
"""
    with pytest.raises(ConfigError, match="system.name"):
        load_config(write_yaml(tmp_path, content))


def test_unsupported_ubuntu_version(tmp_path):
    content = """
system:
  name: test
  ubuntu_version: "20.04"
"""
    with pytest.raises(ConfigError, match="Unsupported ubuntu_version"):
        load_config(write_yaml(tmp_path, content))


# ---------------------------------------------------------------------------
# apt_sources validation
# ---------------------------------------------------------------------------

def test_apt_source_missing_required_field(tmp_path):
    content = """
system:
  name: test
  ubuntu_version: "22.04"
apt_sources:
  - name: nodesource
    uri: https://example.com
    distribution: jammy
    components: [main]
    # key_url intentionally missing
"""
    with pytest.raises(ConfigError, match="missing required fields"):
        load_config(write_yaml(tmp_path, content))


def test_apt_source_empty_components(tmp_path):
    content = """
system:
  name: test
  ubuntu_version: "22.04"
apt_sources:
  - name: nodesource
    uri: https://example.com
    distribution: jammy
    components: []
    key_url: https://example.com/key.gpg
"""
    with pytest.raises(ConfigError, match="non-empty list"):
        load_config(write_yaml(tmp_path, content))


# ---------------------------------------------------------------------------
# packages validation
# ---------------------------------------------------------------------------

def test_package_missing_name(tmp_path):
    content = """
system:
  name: test
  ubuntu_version: "22.04"
packages:
  - version: "1.0"
"""
    with pytest.raises(ConfigError, match="'name' field"):
        load_config(write_yaml(tmp_path, content))


def test_package_empty_name(tmp_path):
    content = """
system:
  name: test
  ubuntu_version: "22.04"
packages:
  - name: "   "
"""
    with pytest.raises(ConfigError, match="must not be empty"):
        load_config(write_yaml(tmp_path, content))