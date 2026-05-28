"""
Tests for idempotency.py
All subprocess calls are mocked — runs on Mac and Ubuntu identically.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from cloudtool.idempotency import (
    is_package_installed,
    apt_source_exists,
    gpg_key_exists,
    file_matches_content,
)


# ---------------------------------------------------------------------------
# is_package_installed
# ---------------------------------------------------------------------------

def test_package_is_installed():
    mock_result = MagicMock()
    mock_result.stdout = "install ok installed"
    with patch("cloudtool.idempotency.subprocess.run", return_value=mock_result):
        assert is_package_installed("curl") is True


def test_package_not_installed():
    mock_result = MagicMock()
    mock_result.stdout = "unknown ok not-installed"
    with patch("cloudtool.idempotency.subprocess.run", return_value=mock_result):
        assert is_package_installed("curl") is False


def test_package_check_no_dpkg(monkeypatch):
    """On macOS, dpkg-query is missing — should return False gracefully."""
    with patch(
        "cloudtool.idempotency.subprocess.run",
        side_effect=FileNotFoundError
    ):
        assert is_package_installed("curl") is False


# ---------------------------------------------------------------------------
# apt_source_exists
# ---------------------------------------------------------------------------

def test_apt_source_exists_list_file(tmp_path):
    sources_dir = tmp_path / "sources.list.d"
    sources_dir.mkdir()
    source_file = sources_dir / "nodesource.list"
    source_file.write_text("deb https://deb.nodesource.com/node_20.x jammy main\n")

    with patch("cloudtool.idempotency._sources_dir", return_value=sources_dir):
        assert apt_source_exists("nodesource", "https://deb.nodesource.com/node_20.x") is True


def test_apt_source_wrong_uri(tmp_path):
    sources_dir = tmp_path / "sources.list.d"
    sources_dir.mkdir()
    source_file = sources_dir / "nodesource.list"
    source_file.write_text("deb https://deb.nodesource.com/node_18.x jammy main\n")

    with patch("cloudtool.idempotency._sources_dir", return_value=sources_dir):
        assert apt_source_exists("nodesource", "https://deb.nodesource.com/node_20.x") is False


def test_apt_source_not_found(tmp_path):
    sources_dir = tmp_path / "sources.list.d"
    sources_dir.mkdir()

    with patch("cloudtool.idempotency._sources_dir", return_value=sources_dir):
        assert apt_source_exists("nodesource", "https://deb.nodesource.com/node_20.x") is False


# ---------------------------------------------------------------------------
# gpg_key_exists
# ---------------------------------------------------------------------------

def test_gpg_key_exists(tmp_path):
    keyrings_dir = tmp_path / "keyrings"
    keyrings_dir.mkdir()
    (keyrings_dir / "nodesource.gpg").write_bytes(b"fake-gpg-data")

    with patch("cloudtool.idempotency._keyrings_dir", return_value=keyrings_dir):
        assert gpg_key_exists("nodesource") is True


def test_gpg_key_missing(tmp_path):
    keyrings_dir = tmp_path / "keyrings"
    keyrings_dir.mkdir()

    with patch("cloudtool.idempotency._keyrings_dir", return_value=keyrings_dir):
        assert gpg_key_exists("nodesource") is False


# ---------------------------------------------------------------------------
# file_matches_content
# ---------------------------------------------------------------------------

def test_file_matches_exact_content(tmp_path):
    f = tmp_path / "test.conf"
    content = "deb https://example.com jammy main\n"
    f.write_text(content)
    assert file_matches_content(f, content) is True


def test_file_content_differs(tmp_path):
    f = tmp_path / "test.conf"
    f.write_text("old content\n")
    assert file_matches_content(f, "new content\n") is False


def test_file_does_not_exist(tmp_path):
    f = tmp_path / "nonexistent.conf"
    assert file_matches_content(f, "anything") is False