# mac-maintenance

Unified macOS maintenance tool that consolidates multiple scripts into a single, non-interactive Python entrypoint with explicit `report`, `dry-run`, and `apply` modes.

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
