# mac-maintenance

Unified macOS maintenance tool that consolidates multiple scripts into a single, non-interactive Python entrypoint with explicit `report`, `dry-run`, and `apply` modes.


## Installation

### Quick Install with Package Managers

**Using [ubi](https://github.com/houseabsolute/ubi):**
```bash
ubi --project joshuascottpaul/mac-maintenance --in ~/.local/bin
```

**Using [bin](https://github.com/marcosnils/bin):**
```bash
bin install github.com/joshuascottpaul/mac-maintenance
```

### Manual Install

```bash
git clone https://github.com/joshuascottpaul/mac-maintenance.git
cd mac-maintenance
./mac_maintenance.py
```

### From Release

```bash
curl -L https://github.com/joshuascottpaul/mac-maintenance/releases/latest/download/mac_maintenance-v0.1.0-darwin-arm64.tar.gz | tar xz
cd mac_maintenance-darwin-arm64
./install.sh
```

## Features

- Single CLI for maintenance tasks
- Explicit modes: `report`, `dry-run`, `apply`
- HTML + CSS report generation
- Safe defaults and explicit action flags
- Pytest suite for core behaviors

## Install

```bash
python3 /Users/jpaul/Desktop/mac_maintenance/mac_maintenance.py --help
```

## Quick Start

Report only (HTML):

```bash
python3 mac_maintenance.py --mode report --task report-html --report-out-dir .
```

Dry-run maintenance tasks:

```bash
python3 mac_maintenance.py --mode dry-run --task brew-maintenance --task cleanup-archives --brew-cleanup --brew-list
```

Apply brew updates:

```bash
python3 mac_maintenance.py --mode apply --task brew-maintenance --brew-update --brew-upgrade
```

## Tests

```bash
pytest tests
```

## Docs

- Software Design Document: `SDD.md`

## License

Apache-2.0
