"""
Tests for apt_manager.py
All subprocess and filesystem calls are mocked.
Runs identically on Mac and Ubuntu.
"""

import pytest
import subprocess
from unittest.mock import patch, MagicMock, call
from pathlib import Path

from cloudtool.config_loader import AptSource, Package
from cloudtool.apt_manager import (
    configure_apt_source,
    install_package,
    update_apt_cache,
    Status,
    _build_source_content,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_source():
    return AptSource(
        name="nodesource",
        uri="https://deb.nodesource.com/node_20.x",
        distribution="jammy",
        components=["main"],
        key_url="https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key",
        enabled=True,
    )


@pytest.fixture
def sample_package():
    return Package(name="curl")


# ---------------------------------------------------------------------------
# install_package
# ---------------------------------------------------------------------------

def test_install_package_already_installed(sample_package):
    with patch("cloudtool.apt_manager.is_package_installed", return_value=True):
        result = install_package(sample_package)
    assert result.status == Status.SKIPPED
    assert result.target == "curl"


def test_install_package_success(sample_package):
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""

    with patch("cloudtool.apt_manager.is_package_installed", return_value=False), \
         patch("cloudtool.apt_manager.subprocess.run", return_value=mock_result):
        result = install_package(sample_package)

    assert result.status == Status.OK
    assert result.target == "curl"


def test_install_package_apt_failure(sample_package):
    with patch("cloudtool.apt_manager.is_package_installed", return_value=False), \
         patch(
             "cloudtool.apt_manager.subprocess.run",
             side_effect=subprocess.CalledProcessError(
                 100, "apt-get", stderr="E: Unable to locate package curl"
             )
         ):
        result = install_package(sample_package)

    assert result.status == Status.FAILED
    assert "Unable to locate package" in result.message


def test_install_package_no_apt(sample_package):
    with patch("cloudtool.apt_manager.is_package_installed", return_value=False), \
         patch("cloudtool.apt_manager.subprocess.run", side_effect=FileNotFoundError):
        result = install_package(sample_package)

    assert result.status == Status.FAILED
    assert "not available" in result.message


# ---------------------------------------------------------------------------
# update_apt_cache
# ---------------------------------------------------------------------------

def test_update_apt_cache_success():
    mock_result = MagicMock()
    mock_result.stdout = ""
    mock_result.stderr = ""

    with patch("cloudtool.apt_manager._run", return_value=mock_result):
        result = update_apt_cache()

    assert result.status == Status.OK
    assert result.target == "apt-cache"


def test_update_apt_cache_failure():
    with patch(
        "cloudtool.apt_manager._run",
        side_effect=subprocess.CalledProcessError(1, "apt-get", stderr="network error")
    ):
        result = update_apt_cache()

    assert result.status == Status.FAILED
    assert "network error" in result.message


def test_update_apt_cache_no_apt():
    with patch("cloudtool.apt_manager._run", side_effect=FileNotFoundError):
        result = update_apt_cache()
    assert result.status == Status.SKIPPED


# ---------------------------------------------------------------------------
# configure_apt_source
# ---------------------------------------------------------------------------

def test_configure_source_already_exists(sample_source):
    with patch("cloudtool.apt_manager.apt_source_exists", return_value=True):
        result = configure_apt_source(sample_source)
    assert result.status == Status.SKIPPED
    assert result.target == "nodesource"


def test_configure_source_success(sample_source, tmp_path):
    keyrings_dir = tmp_path / "keyrings"
    keyrings_dir.mkdir()
    sources_dir = tmp_path / "sources.list.d"
    sources_dir.mkdir()

    with patch("cloudtool.apt_manager.apt_source_exists", return_value=False), \
         patch("cloudtool.apt_manager.gpg_key_exists", return_value=False), \
         patch("cloudtool.apt_manager._fetch_gpg_key", return_value=b"\x99fake-key"), \
         patch("cloudtool.apt_manager._dearmor_key", return_value=b"binary-key"), \
         patch("cloudtool.apt_manager._keyrings_dir", return_value=keyrings_dir), \
         patch("cloudtool.apt_manager._sources_dir", return_value=sources_dir), \
         patch("cloudtool.idempotency._keyrings_dir", return_value=keyrings_dir), \
         patch("cloudtool.idempotency._sources_dir", return_value=sources_dir):
        result = configure_apt_source(sample_source)

    assert result.status == Status.OK
    assert (keyrings_dir / "nodesource.gpg").read_bytes() == b"binary-key"
    assert (sources_dir / "nodesource.sources").exists()


def test_configure_source_key_download_fails(sample_source):
    import urllib.error
    with patch("cloudtool.apt_manager.apt_source_exists", return_value=False), \
         patch("cloudtool.apt_manager.gpg_key_exists", return_value=False), \
         patch(
             "cloudtool.apt_manager._fetch_gpg_key",
             side_effect=urllib.error.URLError("connection refused")
         ):
        result = configure_apt_source(sample_source)

    assert result.status == Status.FAILED
    assert "GPG key download failed" in result.message


def test_configure_source_gpg_key_already_present(sample_source, tmp_path):
    sources_dir = tmp_path / "sources.list.d"
    sources_dir.mkdir()
    keyrings_dir = tmp_path / "keyrings"
    keyrings_dir.mkdir()

    with patch("cloudtool.apt_manager.apt_source_exists", return_value=False), \
         patch("cloudtool.apt_manager.gpg_key_exists", return_value=True), \
         patch("cloudtool.apt_manager._keyrings_dir", return_value=keyrings_dir), \
         patch("cloudtool.apt_manager._sources_dir", return_value=sources_dir), \
         patch("cloudtool.idempotency._keyrings_dir", return_value=keyrings_dir), \
         patch("cloudtool.idempotency._sources_dir", return_value=sources_dir):
        result = configure_apt_source(sample_source)

    assert result.status == Status.OK
    # Key fetch should NOT have been called
    assert not (keyrings_dir / "nodesource.gpg").exists()


# ---------------------------------------------------------------------------
# _build_source_content
# ---------------------------------------------------------------------------

def test_build_source_content(sample_source, tmp_path):
    keyrings_dir = tmp_path / "keyrings"
    with patch("cloudtool.apt_manager._keyrings_dir", return_value=keyrings_dir):
        content = _build_source_content(sample_source, "nodesource")

    assert "URIs: https://deb.nodesource.com/node_20.x" in content
    assert "Suites: jammy" in content
    assert "Components: main" in content
    assert "nodesource.gpg" in content
    assert "Enabled: yes" in content