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
- **Recoverable by default**: deletions move to the macOS Trash (restore via Finder → Put Back); `--permanent` opts into unrecoverable delete
- **Action log**: every apply-mode action is recorded to `~/.mac-maintenance/actions.jsonl`; review it with `--task show-actions`
- Browser cleanup: any Chromium channel (Beta/stable/other) plus Safari cache + site data
- Bundle-ID-based orphan detection across Containers/Preferences/Saved State/App Scripts (report-only)
- Startup-item control: list LaunchAgents, disable login items / launch agents (reversible)
- iCloud eviction census + fix: find `dataless` (evicted) files that stall reads at 0% CPU, re-download them in parallel
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

Apply cache cleanup (moves to Trash — recover via Finder "Put Back"), then review what happened:

```bash
python3 mac-maintenance.py --mode apply --task clean-caches
python3 mac-maintenance.py --mode report --task show-actions        # audit the action log
# ...or reclaim the space immediately with an unrecoverable delete:
python3 mac-maintenance.py --mode apply --task clean-caches --permanent
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

iCloud eviction: census which folders under `~/Documents` have iCloud-evicted (`dataless`)
files — the silent cause of "hangs at 0% CPU" reads — then force-download them.
`report`/`dry-run` are stat-only and never trigger downloads; `apply` reads every evicted
file through a thread pool (network-bound; iCloud may throttle). Useful before moving a
folder out of iCloud scope, since moving evicted placeholders risks the data:

```bash
python3 mac-maintenance.py --mode report --task icloud-eviction                       # ~/Documents
python3 mac-maintenance.py --mode report --task icloud-eviction --eviction-dir ~/Documents/GitHub
python3 mac-maintenance.py --mode apply  --task icloud-eviction --eviction-dir ~/Documents/GitHub --eviction-jobs 16
# spot-check a single file: ls -lO <file>   (evicted files show the "dataless" flag)
```

## Tests

```bash
pytest tests
```

## Docs

- Software Design Document: `SDD.md`

## License

Apache-2.0
