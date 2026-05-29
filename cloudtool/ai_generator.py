"""
ai_generator.py

Generates a valid ubuntu-cloud-tooling YAML config from a natural language
description using intent detection and template composition.

No API key required. Works offline. Demo-safe forever.

Usage:
    python -m cloudtool generate "I need a Python data science environment"
    python -m cloudtool generate "Node.js web server with nginx and postgres"
"""

from pathlib import Path
from cloudtool.config_loader import load_config, ConfigError
from cloudtool.logger import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Package intent map
# Keywords in the prompt → apt packages to include
# ---------------------------------------------------------------------------

INTENT_MAP = [
    # Python / data science
    {
        "keywords": ["python", "data science", "jupyter", "pandas", "numpy", "scipy", "matplotlib"],
        "packages": ["python3", "python3-pip", "python3-venv", "jupyter", "python3-pandas",
                     "python3-numpy", "python3-scipy", "python3-matplotlib", "git"],
    },
    # Node.js — needs custom apt source
    {
        "keywords": ["node", "nodejs", "node.js", "npm", "javascript", "js"],
        "packages": ["nodejs"],
        "sources": [
            {
                "name": "nodesource",
                "uri": "https://deb.nodesource.com/node_20.x",
                "distribution": "{distro}",
                "components": ["main"],
                "key_url": "https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key",
            }
        ],
    },
    # Docker — needs custom apt source
    {
        "keywords": ["docker", "container", "containerize"],
        "packages": ["docker-ce", "docker-ce-cli", "containerd.io", "docker-buildx-plugin"],
        "sources": [
            {
                "name": "docker",
                "uri": "https://download.docker.com/linux/ubuntu",
                "distribution": "{distro}",
                "components": ["stable"],
                "key_url": "https://download.docker.com/linux/ubuntu/gpg",
            }
        ],
    },
    # PostgreSQL — needs custom apt source
    {
        "keywords": ["postgres", "postgresql", "psql"],
        "packages": ["postgresql-16", "postgresql-client-16", "libpq-dev"],
        "sources": [
            {
                "name": "pgdg",
                "uri": "https://apt.postgresql.org/pub/repos/apt",
                "distribution": "{distro}-pgdg",
                "components": ["main"],
                "key_url": "https://www.postgresql.org/media/keys/ACCC4CF8.asc",
            }
        ],
    },
    # Nginx
    {
        "keywords": ["nginx", "web server", "webserver", "reverse proxy"],
        "packages": ["nginx"],
    },
    # Git
    {
        "keywords": ["git", "version control"],
        "packages": ["git"],
    },
    # Build tools
    {
        "keywords": ["build", "build tools", "build-essential", "make", "gcc", "compile"],
        "packages": ["build-essential", "make", "gcc", "g++"],
    },
    # Java
    {
        "keywords": ["java", "jvm", "spring", "maven", "gradle"],
        "packages": ["openjdk-21-jdk", "maven"],
    },
    # Go
    {
        "keywords": ["go", "golang"],
        "packages": ["golang-go"],
    },
    # Rust
    {
        "keywords": ["rust", "cargo"],
        "packages": ["rustc", "cargo"],
    },
    # General dev tools always included
    {
        "keywords": [],   # always matched
        "packages": ["curl", "wget", "vim", "htop", "unzip", "ca-certificates", "gnupg"],
        "_always": True,
    },
]


# ---------------------------------------------------------------------------
# Name slug generation
# ---------------------------------------------------------------------------

SLUG_MAP = [
    (["data science", "jupyter", "pandas", "numpy"], "python-datascience"),
    (["node", "nodejs", "npm"],                       "nodejs-webdev"),
    (["docker", "container"],                         "docker-env"),
    (["postgres", "postgresql"],                      "postgres-db"),
    (["nginx", "web server"],                         "nginx-server"),
    (["java", "spring"],                              "java-dev"),
    (["golang", "go "],                               "go-dev"),
    (["rust", "cargo"],                               "rust-dev"),
    (["python"],                                      "python-dev"),
]


def _make_slug(prompt: str) -> str:
    lowered = prompt.lower()
    for keywords, slug in SLUG_MAP:
        if any(kw in lowered for kw in keywords):
            return slug
    return "ubuntu-dev-env"


# ---------------------------------------------------------------------------
# Core generator
# ---------------------------------------------------------------------------

def _detect_ubuntu_version(prompt: str) -> tuple[str, str]:
    """Return (version, distro_codename) based on prompt or default to 22.04."""
    if "24.04" in prompt or "noble" in prompt.lower():
        return "24.04", "noble"
    return "22.04", "jammy"


def _build_yaml(prompt: str) -> str:
    """
    Match prompt against INTENT_MAP and compose a valid YAML config string.
    Deduplicates packages and sources across matched intents.
    """
    lowered = prompt.lower()
    ubuntu_version, distro = _detect_ubuntu_version(prompt)
    slug = _make_slug(prompt)

    packages: list[str] = []
    sources: list[dict] = []
    seen_packages: set[str] = set()
    seen_sources: set[str] = set()

    for intent in INTENT_MAP:
        always = intent.get("_always", False)
        matched = always or any(kw in lowered for kw in intent["keywords"])

        if matched:
            for pkg in intent.get("packages", []):
                if pkg not in seen_packages:
                    packages.append(pkg)
                    seen_packages.add(pkg)

            for src in intent.get("sources", []):
                if src["name"] not in seen_sources:
                    resolved = {
                        k: v.replace("{distro}", distro) if isinstance(v, str) else v
                        for k, v in src.items()
                    }
                    sources.append(resolved)
                    seen_sources.add(src["name"])

    # Build YAML string manually for full control over formatting
    lines = [
        f"# Generated by ubuntu-cloud-tooling",
        f"# Prompt: {prompt}",
        f"",
        f"system:",
        f"  name: {slug}",
        f'  ubuntu_version: "{ubuntu_version}"',
        f"  update_cache: true",
        f"  upgrade: false",
    ]

    if sources:
        lines.append("")
        lines.append("apt_sources:")
        for src in sources:
            components_str = ", ".join(src["components"])
            lines += [
                f"  - name: {src['name']}",
                f"    uri: {src['uri']}",
                f"    distribution: {src['distribution']}",
                f"    components: [{components_str}]",
                f"    key_url: {src['key_url']}",
                f"    enabled: true",
            ]

    if packages:
        lines.append("")
        lines.append("packages:")
        for pkg in packages:
            lines.append(f"  - name: {pkg}")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_config(prompt: str, output_path: Path) -> int:
    """
    Generate a YAML config from a natural language prompt.
    Validates result through config_loader before saving.

    Args:
        prompt:      Natural language description of desired environment
        output_path: Where to write the generated YAML

    Returns:
        0 on success, 1 on failure
    """
    log.info("AI    generating config for: '%s'", prompt)
    print(f"\nGenerating config for: \"{prompt}\"\n")

    yaml_text = _build_yaml(prompt)

    # Validate through config_loader — guarantees the output is applyable
    log.info("AI    validating generated config")
    tmp_path = output_path.parent / f".tmp_{output_path.name}"
    try:
        tmp_path.write_text(yaml_text, encoding="utf-8")
        config = load_config(tmp_path)
    except (ConfigError, Exception) as exc:
        log.error("AI    generated config failed validation: %s", exc)
        tmp_path.unlink(missing_ok=True)
        return 1
    finally:
        tmp_path.unlink(missing_ok=True)

    output_path.write_text(yaml_text, encoding="utf-8")

    print("=" * 52)
    print(f"  Generated config : {output_path}")
    print(f"  System name      : {config.system.name}")
    print(f"  Ubuntu version   : {config.system.ubuntu_version}")
    print(f"  Packages         : {len(config.packages)}")
    print(f"  APT sources      : {len(config.apt_sources)}")
    print("=" * 52)
    print(f"\nReview it:  cat {output_path}")
    print(f"Apply it:   sudo python -m cloudtool apply {output_path}\n")

    log.info("AI    config written to %s", output_path)
    return 0