"""
idempotency.py

Checks current system state before any action.
Every check returns True if the desired state already exists (skip),
False if action is needed.

All subprocess calls are isolated here so tests can mock them cleanly.
"""

import subprocess
import hashlib
from pathlib import Path

from cloudtool.logger import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Package state
# ---------------------------------------------------------------------------

def is_package_installed(package_name: str) -> bool:
    """
    Returns True if the package is already installed at any version.
    Uses dpkg-query — available on all Debian/Ubuntu systems.

    Args:
        package_name: The apt package name, e.g. "curl"
    """
    try:
        result = subprocess.run(
            ["dpkg-query", "-W", "-f=${Status}", package_name],
            capture_output=True,
            text=True,
        )
        installed = "install ok installed" in result.stdout
        if installed:
            log.debug("SKIP  package '%s' already installed", package_name)
        else:
            log.debug("NEED  package '%s' not installed", package_name)
        return installed

    except FileNotFoundError:
        # dpkg-query not available (e.g. running on macOS in dev/test)
        log.debug("dpkg-query not found — assuming package '%s' not installed", package_name)
        return False


# ---------------------------------------------------------------------------
# APT source state
# ---------------------------------------------------------------------------

def _sources_dir() -> Path:
    return Path("/etc/apt/sources.list.d")


def _keyrings_dir() -> Path:
    return Path("/usr/share/keyrings")


def apt_source_exists(source_name: str, uri: str) -> bool:
    """
    Returns True if an apt source with this name and URI already exists.

    Checks for both legacy .list format and modern .sources format.
    Ubuntu 22.04+ prefers the signed-by / .sources style, but we check both.

    Args:
        source_name: The logical name, e.g. "nodesource"
        uri:         The repository URI to match against
    """
    sources_dir = _sources_dir()

    # Check both file extensions
    for ext in (".list", ".sources"):
        source_file = sources_dir / f"{source_name}{ext}"
        if source_file.exists():
            content = source_file.read_text(encoding="utf-8")
            if uri in content:
                log.debug("SKIP  apt source '%s' already configured", source_name)
                return True

    log.debug("NEED  apt source '%s' not found", source_name)
    return False


def gpg_key_exists(source_name: str) -> bool:
    """
    Returns True if the GPG keyring file for this source already exists.
    Ubuntu 22.04+ stores keys as binary .gpg files in /usr/share/keyrings/.

    Args:
        source_name: Used to derive the keyring filename, e.g. "nodesource"
    """
    key_file = _keyrings_dir() / f"{source_name}.gpg"
    exists = key_file.exists()
    if exists:
        log.debug("SKIP  GPG key '%s' already present", source_name)
    else:
        log.debug("NEED  GPG key '%s' not found", source_name)
    return exists


# ---------------------------------------------------------------------------
# File content state (generic — used for config file writes)
# ---------------------------------------------------------------------------

def file_matches_content(path: Path, expected_content: str) -> bool:
    """
    Returns True if the file at path already has exactly the expected content.
    Used to avoid rewriting files that are already correct.

    Args:
        path:             Path to the file to check
        expected_content: The content we would write
    """
    if not path.exists():
        return False

    existing_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    expected_hash = hashlib.sha256(expected_content.encode()).hexdigest()
    match = existing_hash == expected_hash

    if match:
        log.debug("SKIP  file '%s' already has correct content", path)
    else:
        log.debug("NEED  file '%s' exists but content differs", path)

    return match