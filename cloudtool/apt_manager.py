"""
apt_manager.py

Core engine for:
  1. Configuring apt sources (GPG keys + .sources files, Ubuntu 22.04+ style)
  2. Running apt-get update
  3. Installing deb packages with dependency resolution

All functions return an ActionResult describing what happened.
Idempotency checks run before every mutating action.
"""

import subprocess
import urllib.request
import urllib.error
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from cloudtool.config_loader import AptSource, Package
from cloudtool.idempotency import (
    is_package_installed,
    apt_source_exists,
    gpg_key_exists,
    file_matches_content,
    _sources_dir,
    _keyrings_dir,
)
from cloudtool.logger import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Result type — every public function returns one of these
# ---------------------------------------------------------------------------

class Status(Enum):
    OK      = "OK"       # action was taken successfully
    SKIPPED = "SKIPPED"  # already in desired state, nothing done
    FAILED  = "FAILED"   # action attempted but failed


@dataclass
class ActionResult:
    status: Status
    target: str           # package name, source name, etc.
    message: str = ""     # human-readable detail


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """
    Run a shell command, capturing stdout and stderr.
    Logs the command at DEBUG level before running.
    """
    log.debug("RUN   %s", " ".join(cmd))
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=check,
    )


def _fetch_gpg_key(key_url: str) -> bytes:
    """Download a GPG key from key_url and return raw bytes."""
    log.debug("FETCH GPG key from %s", key_url)
    with urllib.request.urlopen(key_url, timeout=15) as resp:  # noqa: S310
        return resp.read()


def _dearmor_key(raw_key_bytes: bytes) -> bytes:
    """
    Convert an ASCII-armored GPG key to binary using gpg --dearmor.
    Ubuntu 22.04+ requires binary .gpg files in /usr/share/keyrings/.
    If the key is already binary (starts with 0x99), return as-is.
    """
    # Binary OpenPGP packets start with 0x99 or 0x98
    if raw_key_bytes[0] in (0x99, 0x98, 0x80 | 0x18, 0x80 | 0x19):
        return raw_key_bytes

    result = subprocess.run(
        ["gpg", "--dearmor"],
        input=raw_key_bytes,
        capture_output=True,
        check=True,
    )
    return result.stdout


def _build_source_content(source: AptSource, key_name: str) -> str:
    """
    Build the content of a modern Ubuntu 22.04+ apt .sources file.
    Uses the signed-by field pointing to the keyring in /usr/share/keyrings/.
    """
    components = " ".join(source.components)
    keyring_path = _keyrings_dir() / f"{key_name}.gpg"
    return (
        f"Types: deb\n"
        f"URIs: {source.uri}\n"
        f"Suites: {source.distribution}\n"
        f"Components: {components}\n"
        f"Signed-By: {keyring_path}\n"
        f"Enabled: {'yes' if source.enabled else 'no'}\n"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def configure_apt_source(source: AptSource) -> ActionResult:
    """
    Idempotently configure an apt source.

    Steps:
      1. Check if source already exists with correct URI → skip if so
      2. Download and dearmor the GPG key → write to /usr/share/keyrings/
      3. Write a .sources file to /etc/apt/sources.list.d/

    Args:
        source: An AptSource dataclass from config_loader

    Returns:
        ActionResult with status OK, SKIPPED, or FAILED
    """
    log.info("SOURCE checking '%s' (%s)", source.name, source.uri)

    # Idempotency check — if source file already has this URI, skip everything
    if apt_source_exists(source.name, source.uri):
        return ActionResult(
            status=Status.SKIPPED,
            target=source.name,
            message="apt source already configured",
        )

    try:
        # Step 1 — GPG key (only if not already present)
        if not gpg_key_exists(source.name):
            log.info("SOURCE fetching GPG key for '%s'", source.name)
            raw_key = _fetch_gpg_key(source.key_url)
            binary_key = _dearmor_key(raw_key)

            key_path = _keyrings_dir() / f"{source.name}.gpg"
            key_path.parent.mkdir(parents=True, exist_ok=True)
            key_path.write_bytes(binary_key)
            log.info("SOURCE wrote GPG key → %s", key_path)
        else:
            log.info("SOURCE GPG key for '%s' already present, skipping", source.name)

        # Step 2 — .sources file
        source_content = _build_source_content(source, source.name)
        source_file = _sources_dir() / f"{source.name}.sources"

        if file_matches_content(source_file, source_content):
            log.info("SOURCE file for '%s' unchanged, skipping write", source.name)
        else:
            source_file.parent.mkdir(parents=True, exist_ok=True)
            source_file.write_text(source_content, encoding="utf-8")
            log.info("SOURCE wrote → %s", source_file)

        return ActionResult(
            status=Status.OK,
            target=source.name,
            message=f"configured apt source → {source_file}",
        )

    except urllib.error.URLError as exc:
        log.error("SOURCE failed to fetch GPG key for '%s': %s", source.name, exc)
        return ActionResult(
            status=Status.FAILED,
            target=source.name,
            message=f"GPG key download failed: {exc}",
        )
    except OSError as exc:
        log.error("SOURCE failed to write files for '%s': %s", source.name, exc)
        return ActionResult(
            status=Status.FAILED,
            target=source.name,
            message=f"File write failed: {exc}",
        )
    except subprocess.CalledProcessError as exc:
        log.error("SOURCE gpg --dearmor failed for '%s': %s", source.name, exc.stderr)
        return ActionResult(
            status=Status.FAILED,
            target=source.name,
            message=f"GPG dearmor failed: {exc.stderr}",
        )


def update_apt_cache() -> ActionResult:
    """
    Run apt-get update to refresh package lists.

    Returns:
        ActionResult with status OK or FAILED
    """
    log.info("CACHE running apt-get update")
    try:
        result = _run(["apt-get", "update", "-qq"])
        log.info("CACHE apt-get update complete")
        return ActionResult(status=Status.OK, target="apt-cache", message=result.stdout.strip())
    except subprocess.CalledProcessError as exc:
        log.error("CACHE apt-get update failed: %s", exc.stderr)
        return ActionResult(
            status=Status.FAILED,
            target="apt-cache",
            message=f"apt-get update failed: {exc.stderr.strip()}",
        )
    except FileNotFoundError:
        log.warning("CACHE apt-get not found (non-Ubuntu environment), skipping")
        return ActionResult(
            status=Status.SKIPPED,
            target="apt-cache",
            message="apt-get not available on this platform",
        )


def install_package(package: Package) -> ActionResult:
    """
    Idempotently install a deb package via apt-get.

    Checks if already installed first. If not, runs:
        apt-get install -y <name>

    apt handles full dependency resolution automatically.

    Args:
        package: A Package dataclass from config_loader

    Returns:
        ActionResult with status OK, SKIPPED, or FAILED
    """
    log.info("PKG   checking '%s'", package.name)

    # Idempotency check
    if is_package_installed(package.name):
        return ActionResult(
            status=Status.SKIPPED,
            target=package.name,
            message="already installed",
        )

    log.info("PKG   installing '%s'", package.name)
    try:
        env = {"DEBIAN_FRONTEND": "noninteractive"}
        result = subprocess.run(
            ["apt-get", "install", "-y", package.name],
            capture_output=True,
            text=True,
            check=True,
            env={**__import__("os").environ, **env},
        )
        log.info("PKG   installed '%s' successfully", package.name)
        return ActionResult(
            status=Status.OK,
            target=package.name,
            message=f"installed successfully",
        )
    except subprocess.CalledProcessError as exc:
        log.error("PKG   failed to install '%s': %s", package.name, exc.stderr.strip())
        return ActionResult(
            status=Status.FAILED,
            target=package.name,
            message=f"apt-get install failed: {exc.stderr.strip()}",
        )
    except FileNotFoundError:
        log.warning("PKG   apt-get not found, cannot install '%s'", package.name)
        return ActionResult(
            status=Status.FAILED,
            target=package.name,
            message="apt-get not available on this platform",
        )