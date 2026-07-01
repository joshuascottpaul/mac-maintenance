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
./mac-maintenance.py
```

### From Release

```bash
curl -L https://github.com/joshuascottpaul/mac-maintenance/releases/latest/download/mac-maintenance-v0.1.0-darwin-arm64.tar.gz | tar xz
cd mac-maintenance-darwin-arm64
./install.sh
```

## Features

- Single CLI for maintenance tasks
- Explicit modes: `report`, `dry-run`, `apply`
- HTML + CSS report generation
- Safe defaults and explicit action flags
- Disk cleanup: caches, Trash, logs, iOS backups (age-guarded, dry-run by default)
- Browser cleanup: any Chromium channel (Beta/stable/other) plus Safari cache + site data
- Bundle-ID-based orphan detection across Containers/Preferences/Saved State/App Scripts (report-only)
- Startup-item control: list LaunchAgents, disable login items / launch agents (reversible)
- Pytest suite for core behaviors

## Quick Start

Report only (HTML):

```bash
python3 mac-maintenance.py --mode report --task report-html --report-out-dir .
```

Dry-run maintenance tasks:

```bash
python3 mac-maintenance.py --mode dry-run --task brew-maintenance --task cleanup-archives --brew-cleanup --brew-list
```

Apply brew updates:

```bash
python3 mac-maintenance.py --mode apply --task brew-maintenance --brew-update --brew-upgrade
```

Dry-run disk cleanup (caches, Trash, logs):

```bash
python3 mac-maintenance.py --mode dry-run --task clean-caches --task empty-trash --task clean-logs
```

Find potential app leftovers by bundle ID (report-only, no deletion):

```bash
python3 mac-maintenance.py --mode report --task find-bundle-orphans
```

Clean stable Chrome (not just Beta) and Safari caches (dry-run):

```bash
python3 mac-maintenance.py --mode dry-run --task chrome-cleanup \
  --chrome-dir "$HOME/Library/Application Support/Google/Chrome" \
  --chrome-process-name "Google Chrome"
python3 mac-maintenance.py --mode dry-run --task safari-cleanup
```

List startup LaunchAgents (report-only), then disable a specific one (reversible):

```bash
python3 mac-maintenance.py --mode report --task find-launch-agents
python3 mac-maintenance.py --mode apply --task disable-launch-agent --launch-agent com.example.updater
python3 mac-maintenance.py --mode apply --task disable-login-item --login-item com.example.helper.loginitem
# undo with: launchctl enable gui/$UID/<label>
```

## Tests

```bash
pytest tests
```

## Docs

- Software Design Document: `SDD.md`

## License

Apache-2.0
