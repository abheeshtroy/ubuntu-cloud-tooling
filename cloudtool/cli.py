"""
cli.py
Entrypoint for ubuntu-cloud-tooling.

Usage:
    sudo python -m cloudtool apply   config/example.yaml
    sudo python -m cloudtool verify  config/example.yaml
         python -m cloudtool generate "I need a python dev environment"
"""

import argparse
import sys
from pathlib import Path

from cloudtool.config_loader import load_config, ConfigError
from cloudtool.logger import setup_logging, get_logger
from cloudtool.apt_manager import configure_apt_source, update_apt_cache, install_package
from cloudtool.reporter import RunReport

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def cmd_apply(args: argparse.Namespace) -> int:
    """
    Apply the config: configure sources, update cache, install packages.
    Requires sudo on Ubuntu. Safe to run multiple times (idempotent).
    """
    log.info("=== ubuntu-cloud-tooling apply ===")
    log.info("Config: %s", args.config)

    try:
        config = load_config(args.config)
    except (ConfigError, FileNotFoundError) as exc:
        log.error("Failed to load config: %s", exc)
        return 1

    log.info(
        "Loaded config '%s' — %d source(s), %d package(s)",
        config.system.name,
        len(config.apt_sources),
        len(config.packages),
    )

    report = RunReport()

    # Step 1 — Configure apt sources
    for source in config.apt_sources:
        result = configure_apt_source(source)
        report.record_source(result)

    # Step 2 — Update apt cache
    if config.system.update_cache:
        result = update_apt_cache()
        report.record_cache(result)
        if result.status.value == "FAILED":
            log.warning("apt-get update failed — package installs may fail")

    # Step 3 — Install packages
    for package in config.packages:
        result = install_package(package)
        report.record_package(result)

    report.print_summary(log_file=args.log_file)
    return 1 if report.has_failures() else 0


def cmd_verify(args: argparse.Namespace) -> int:
    """
    Dry-run: load and validate config, check current system state.
    Does NOT install anything. Does NOT require sudo.
    """
    log.info("=== ubuntu-cloud-tooling verify (dry-run) ===")

    try:
        config = load_config(args.config)
    except (ConfigError, FileNotFoundError) as exc:
        log.error("Failed to load config: %s", exc)
        return 1

    from cloudtool.idempotency import is_package_installed, apt_source_exists

    print(f"\nConfig: {args.config}")
    print(f"System: {config.system.name} (Ubuntu {config.system.ubuntu_version})\n")

    print("APT Sources:")
    for src in config.apt_sources:
        exists = apt_source_exists(src.name, src.uri)
        tag = "OK      " if exists else "MISSING "
        print(f"  [{tag}] {src.name}  →  {src.uri}")

    print("\nPackages:")
    for pkg in config.packages:
        installed = is_package_installed(pkg.name)
        tag = "OK      " if installed else "MISSING "
        print(f"  [{tag}] {pkg.name}")

    print()
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    """
    Use Gemini AI to generate a config YAML from a natural language description.
    Does NOT require sudo.
    """
    from cloudtool.ai_generator import generate_config
    return generate_config(args.prompt, args.output)


# ---------------------------------------------------------------------------
# CLI definition
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cloudtool",
        description="Ubuntu Cloud Tooling — reproducible apt-based system configuration",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=Path("cloudtool.log"),
        help="Path to write log file (default: ./cloudtool.log)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # apply
    apply_parser = subparsers.add_parser(
        "apply",
        help="Apply config: configure sources and install packages (requires sudo)",
    )
    apply_parser.add_argument("config", type=Path, help="Path to YAML config file")

    # verify
    verify_parser = subparsers.add_parser(
        "verify",
        help="Dry-run: check current system state against config (no changes made)",
    )
    verify_parser.add_argument("config", type=Path, help="Path to YAML config file")

    # generate
    generate_parser = subparsers.add_parser(
        "generate",
        help="Generate a config YAML from a natural language description (uses Gemini AI)",
    )
    generate_parser.add_argument("prompt", type=str, help="Natural language environment description")
    generate_parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path("generated_config.yaml"),
        help="Output path for generated YAML (default: ./generated_config.yaml)",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    setup_logging(log_file=args.log_file, verbose=args.verbose)

    handlers = {
        "apply":    cmd_apply,
        "verify":   cmd_verify,
        "generate": cmd_generate,
    }

    sys.exit(handlers[args.command](args))


if __name__ == "__main__":
    main()