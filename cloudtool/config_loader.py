"""
config_loader.py
Parses and validates the YAML configuration file.
Returns a structured Config object consumed by all other modules.
"""

import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data classes — typed representation of the YAML structure
# ---------------------------------------------------------------------------

@dataclass
class SystemConfig:
    name: str
    ubuntu_version: str
    update_cache: bool = True
    upgrade: bool = False


@dataclass
class AptSource:
    name: str
    uri: str
    distribution: str
    components: list[str]
    key_url: str
    enabled: bool = True


@dataclass
class Package:
    name: str


@dataclass
class Config:
    system: SystemConfig
    packages: list[Package] = field(default_factory=list)
    apt_sources: list[AptSource] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

SUPPORTED_UBUNTU_VERSIONS = {"22.04", "24.04"}

REQUIRED_SOURCE_FIELDS = {"name", "uri", "distribution", "components", "key_url"}


def _validate_system(system_raw: dict) -> SystemConfig:
    """Validate the [system] block and return a SystemConfig."""
    if not isinstance(system_raw, dict):
        raise ConfigError("'system' block must be a mapping")

    for field_name in ("name", "ubuntu_version"):
        if field_name not in system_raw:
            raise ConfigError(f"'system.{field_name}' is required")

    version = str(system_raw["ubuntu_version"])
    if version not in SUPPORTED_UBUNTU_VERSIONS:
        raise ConfigError(
            f"Unsupported ubuntu_version '{version}'. "
            f"Supported: {sorted(SUPPORTED_UBUNTU_VERSIONS)}"
        )

    return SystemConfig(
        name=str(system_raw["name"]),
        ubuntu_version=version,
        update_cache=bool(system_raw.get("update_cache", True)),
        upgrade=bool(system_raw.get("upgrade", False)),
    )


def _validate_apt_sources(sources_raw: list) -> list[AptSource]:
    """Validate the [apt_sources] block and return a list of AptSource."""
    if not isinstance(sources_raw, list):
        raise ConfigError("'apt_sources' must be a list")

    sources = []
    for i, src in enumerate(sources_raw):
        if not isinstance(src, dict):
            raise ConfigError(f"apt_sources[{i}] must be a mapping")

        missing = REQUIRED_SOURCE_FIELDS - src.keys()
        if missing:
            raise ConfigError(
                f"apt_sources[{i}] ('{src.get('name', '?')}') "
                f"is missing required fields: {sorted(missing)}"
            )

        components = src["components"]
        if not isinstance(components, list) or not components:
            raise ConfigError(
                f"apt_sources[{i}].components must be a non-empty list"
            )

        sources.append(AptSource(
            name=str(src["name"]),
            uri=str(src["uri"]),
            distribution=str(src["distribution"]),
            components=[str(c) for c in components],
            key_url=str(src["key_url"]),
            enabled=bool(src.get("enabled", True)),
        ))

    return sources


def _validate_packages(packages_raw: list) -> list[Package]:
    """Validate the [packages] block and return a list of Package."""
    if not isinstance(packages_raw, list):
        raise ConfigError("'packages' must be a list")

    packages = []
    for i, pkg in enumerate(packages_raw):
        if not isinstance(pkg, dict) or "name" not in pkg:
            raise ConfigError(
                f"packages[{i}] must be a mapping with a 'name' field"
            )
        name = str(pkg["name"]).strip()
        if not name:
            raise ConfigError(f"packages[{i}].name must not be empty")
        packages.append(Package(name=name))

    return packages


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class ConfigError(Exception):
    """Raised when the configuration file is invalid."""


def load_config(path: str | Path) -> Config:
    """
    Load and validate a YAML config file.

    Args:
        path: Path to the YAML configuration file.

    Returns:
        A validated Config object.

    Raises:
        ConfigError: If the file is missing, unreadable, or invalid.
        FileNotFoundError: If the path does not exist.
    """
    config_path = Path(path)

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"Failed to parse YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError("Config file must be a YAML mapping at the top level")

    if "system" not in raw:
        raise ConfigError("Config file must contain a 'system' block")

    system = _validate_system(raw["system"])
    apt_sources = _validate_apt_sources(raw.get("apt_sources", []))
    packages = _validate_packages(raw.get("packages", []))

    return Config(system=system, apt_sources=apt_sources, packages=packages)