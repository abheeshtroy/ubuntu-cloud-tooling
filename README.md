# Ubuntu Cloud Tooling

A Python CLI tool for reproducible, idempotent Ubuntu system configuration.
Declare your environment in YAML — packages, apt sources, GPG keys — and
converge any Ubuntu 22.04/24.04 LTS machine to that state. Running it twice
changes nothing. This is the same convergent-state model used by
[cloud-init](https://cloud-init.io/) and Ansible.

```bash
# Describe what you want
python -m cloudtool generate "Python data science environment with jupyter and numpy"

# Check current state without changing anything
python -m cloudtool verify generated_config.yaml

# Apply it (requires sudo on Ubuntu)
sudo python -m cloudtool apply generated_config.yaml
```

---

## Features

- **Declarative YAML config** — specify packages and apt sources in one file
- **Idempotent** — checks system state before every action; safe to run repeatedly
- **apt source management** — writes Ubuntu 22.04+ signed-by `.sources` files, fetches and dearmors GPG keys
- **Full dependency resolution** — delegates to `apt-get`, which handles the dep graph
- **Structured logging** — every action logged to stdout and file with timestamp and status
- **Dry-run mode** — `verify` subcommand checks state without making changes
- **Intent-based config generation** — `generate` subcommand produces valid YAML from plain English
- **38 tests** — full coverage of config validation, idempotency logic, and apt operations; mocked so tests run on any platform

---

## Installation

```bash
git clone https://github.com/abheeshtroy/ubuntu-cloud-tooling.git
cd ubuntu-cloud-tooling
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

---

## Usage

### Generate a config from plain English

```bash
python -m cloudtool generate "Node.js 20 web server with nginx and postgres"
```

Output (`generated_config.yaml`):

```yaml
system:
  name: nodejs-webdev
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
  - name: pgdg
    uri: https://apt.postgresql.org/pub/repos/apt
    distribution: jammy-pgdg
    components: [main]
    key_url: https://www.postgresql.org/media/keys/ACCC4CF8.asc
    enabled: true

packages:
  - name: nodejs
  - name: postgresql-16
  - name: nginx
  - name: curl
  - name: build-essential
```

### Verify current state (dry-run, no sudo needed)

```bash
python -m cloudtool verify config/example.yaml
```

```
Config: config/example.yaml
System: dev-workstation (Ubuntu 22.04)

APT Sources:
  [MISSING ] nodesource  →  https://deb.nodesource.com/node_20.x

Packages:
  [OK      ] curl
  [OK      ] git
  [MISSING ] nodejs
```

### Apply a config (requires sudo on Ubuntu)

```bash
sudo python -m cloudtool apply config/example.yaml
```

```
2026-05-28 22:10:01  INFO  cloudtool.apt_manager  SOURCE checking 'nodesource'
2026-05-28 22:10:02  INFO  cloudtool.apt_manager  SOURCE wrote GPG key → /usr/share/keyrings/nodesource.gpg
2026-05-28 22:10:02  INFO  cloudtool.apt_manager  PKG   installing 'nodejs'
2026-05-28 22:10:08  INFO  cloudtool.apt_manager  PKG   installed 'nodejs' successfully

====================================================
  Ubuntu Cloud Tooling — Run Summary
====================================================
  Packages :   5 installed    2 skipped    0 failed
  Sources  :   1 added        0 skipped    0 failed
  Duration : 7.3s
  Status   : SUCCESS
====================================================
```

### Options

```
python -m cloudtool --help

usage: cloudtool [-h] [--log-file LOG_FILE] [--verbose] {apply,verify,generate} ...

subcommands:
  apply     Apply config — configure sources and install packages (requires sudo)
  verify    Dry-run — check current system state against config, no changes made
  generate  Generate a config YAML from a natural language description
```

---

## Config file reference

```yaml
system:
  name: my-environment         # short identifier
  ubuntu_version: "22.04"      # "22.04" or "24.04"
  update_cache: true           # run apt-get update before installing
  upgrade: false               # run apt-get upgrade (usually false)

apt_sources:                   # omit section if using only default Ubuntu repos
  - name: nodesource           # used as filename: /etc/apt/sources.list.d/nodesource.sources
    uri: https://deb.nodesource.com/node_20.x
    distribution: jammy        # jammy = 22.04, noble = 24.04
    components: [main]
    key_url: https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key
    enabled: true

packages:
  - name: curl                 # exact apt package names
  - name: nodejs
```

---

## Architecture

```
cloudtool/
├── cli.py            # argparse entrypoint — apply / verify / generate subcommands
├── config_loader.py  # YAML parsing and validation → typed Config dataclass
├── apt_manager.py    # apt source configuration + package installation
├── idempotency.py    # state checks via dpkg-query and file inspection
├── logger.py         # structured logging to stdout + file
├── reporter.py       # run summary after apply
└── ai_generator.py   # intent-based YAML generation from natural language
```

**Idempotency** is enforced at every step: `dpkg-query` checks package state,
file content hashing checks source files, GPG key presence is verified before
any download. Re-running against an already-configured system produces zero
changes and exits cleanly.

**apt source handling** follows Ubuntu 22.04+ conventions: binary `.gpg`
keyrings in `/usr/share/keyrings/` with `Signed-By` fields in `.sources`
files, not the deprecated `apt-key` approach.

---

## Running tests

Tests are fully mocked — no apt, no sudo, runs on macOS and Ubuntu:

```bash
pytest -v
```

```
38 passed in 0.07s
```

---

## Supported environments (generate subcommand)

| Prompt keywords | Packages | Custom apt source |
|---|---|---|
| python, jupyter, pandas, numpy | python3, pip, jupyter, numpy... | none |
| node, nodejs, npm | nodejs | nodesource |
| docker, container | docker-ce, containerd... | docker official |
| postgres, postgresql | postgresql-16, libpq-dev | pgdg |
| nginx, web server | nginx | none |
| java, spring | openjdk-21-jdk, maven | none |
| go, golang | golang-go | none |
| rust, cargo | rustc, cargo | none |