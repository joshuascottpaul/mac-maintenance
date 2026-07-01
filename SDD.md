# Software Design Document (SDD)

**Project**: Unified macOS Maintenance Tool

**Location**: `mac-maintenance.py` (repo root)

**Version**: Draft 1

**Date**: 2026-02-09

---

**Executive Summary**

This SDD defines a unified macOS maintenance tool that consolidates multiple scripts into a single Python entrypoint with explicit `report`, `dry-run`, and `apply` modes. It emphasizes safe defaults, non-interactive execution, explicit task selection, and optional HTML reporting. The design supports all legacy tasks through discrete, flag-gated modules while preserving read-only behavior unless `apply` is explicitly chosen.

---

**1. Overview**

This document describes the design for a unified macOS maintenance tool that consolidates existing maintenance scripts into a single Python entrypoint with explicit modes and flags. The tool supports a read-only report mode, a dry-run mode that shows intended actions, and an apply mode that performs changes only when explicitly requested.

The design prioritizes safety, transparency, and repeatability, with non-interactive execution and explicit task selection.

---

**2. Goals**

- Provide a single executable that covers all legacy maintenance tasks.
- Support three explicit modes: `report`, `dry-run`, and `apply`.
- Require explicit task selection and explicit action flags for any changes.
- Produce an HTML + CSS maintenance report consistent with prior report output.
- Ensure safe defaults and predictable behavior in non-interactive runs.

---

**3. Non-Goals**

- Automatic scheduling or background execution.
- Remote management or fleet-level orchestration.
- GUI application integration beyond the HTML report.
- Package distribution or installation logic.

---

**4. Stakeholders and Users**

- Primary user: macOS power user running local maintenance and audits.
- Secondary user: future collaborators via GitHub.

---

**5. Assumptions**

- The tool is run on macOS.
- Python 3 is available.
- The user has sufficient permissions for the selected tasks.
- Network use is explicitly enabled via flags.

---

**6. Functional Requirements**

- Provide a single entrypoint: `mac-maintenance.py`.
- Support modes: `report`, `dry-run`, `apply`.
- Support tasks:
- `report-html`
- `brew-maintenance`
- `find-orphans`
- `archive-orphans`
- `cleanup-archives`
- `chrome-cleanup`
- `copy-speed-test`
- `clean-caches`
- `empty-trash`
- `clean-logs`
- `clean-ios-backups`
- `find-bundle-orphans`
- Support explicit flags for maintenance actions (brew update/upgrade/cleanup/etc.).
- Generate HTML + CSS report output in a specified directory.
- Preserve read-only behavior unless `--mode apply` is used.

---

**7. Non-Functional Requirements**

- Safety: no changes in `report` or `dry-run` modes.
- Transparency: log all actions and decisions.
- Determinism: behavior should be stable given the same inputs.
- Portability: use standard system binaries only.
- Performance: avoid heavy scans unless explicitly requested.

---

**8. Architecture**

The tool is a single Python module with the following layers.

- CLI layer: argument parsing and task selection.
- Task layer: functions implementing each maintenance task.
- Reporting layer: HTML/CSS generation and command execution output rendering.
- Utilities layer: shared helpers (logging, safe path validation, execution wrappers).

---

**9. Entry Points**

- Main entrypoint: `mac-maintenance.py`
- Example invocation:
- `python3 mac-maintenance.py --mode report --task report-html --report-out-dir .`

---

**10. Modes**

- `report`: run read-only checks and generate report; no changes allowed.
- `dry-run`: compute what would change and log intended actions; no changes.
- `apply`: perform requested actions; only tasks and flags explicitly set will run.

Mode behavior rules.

- `report` is the default when no mode is specified.
- For any task that can modify state, `report` behaves like read-only checks only.
- `dry-run` must log intended filesystem or system changes without performing them.
- `apply` must only execute actions that correspond to explicit flags.

---

**11. Tasks**

**11.1 `report-html`**

- Generates HTML and CSS outputs.
- Includes sections for system, disk, brew, updates, startup items, security, backups, battery, and logs.
- Optional scopes:
- `--include-network` for network commands.
- `--include-heavy` for disk scans.
- `--include-profiler` for system_profiler sections.
- `--include-logs` for log scanning.

**11.2 `brew-maintenance`**

- Optional operations gated by flags:
- `--brew-update`
- `--brew-upgrade`
- `--brew-upgrade-cask`
- `--brew-autoremove`
- `--brew-cleanup`
- `--brew-doctor`
- `--brew-missing`
- `--brew-list`
- `--brew-cask-list`
- `--brew-untap`
- `--brew-fix-missing-casks`
- Output files:
- `--brew-list-file`
- `--brew-cask-file`

**11.3 `find-orphans`**

- Scans Application Support directories.
- Compares to installed `/Applications/*.app` names.
- Filters system directories via a skip regex.
- Prints a bounded list of potential orphans and summary count.

**11.4 `archive-orphans`**

- Archives selected Application Support folders into zip files.
- Adds deletion date suffix based on `--archive-days`.
- Removes original folders only in `apply` mode.

**11.5 `cleanup-archives`**

- Deletes archived zip files whose delete date is past.
- Controlled by `--archive-dir`.

**11.6 `chrome-cleanup`**

- Cleans cache-like directories inside Chrome Beta profiles.
- Uses `--kill-chrome` to allow closing Chrome in apply mode.
- Only operates inside the validated Chrome profile directory.

**11.7 `copy-speed-test`**

- Runs rsync to copy a source to destination.
- Calculates throughput from source size and duration.
- Does not run unless in `apply` mode.
- `--copy-src` and `--copy-dst` have no default; both must be passed explicitly or the
  task logs an error and exits without touching the filesystem.

**11.8 `clean-caches`**

- Deletes immediate child entries of `--cache-dir` (default `~/Library/Caches`).
- Skips any entry modified within `--cache-min-age` seconds (default 300) to avoid
  racing an app that is actively writing to its cache.
- Reports per-entry and total size before acting; `dry-run`/`report` only log what
  would be deleted.

**11.9 `empty-trash`**

- Deletes immediate child entries of `--trash-dir` (default `~/.Trash`).
- Same content-deletion mechanics as `clean-caches`, no age guard (items are
  already user-deleted).

**11.10 `clean-logs`**

- Deletes immediate child entries of `--logs-dir` (default `~/Library/Logs`).
- Same age-guard mechanics as `clean-caches`, via `--logs-min-age` (default 300s).

**11.11 `clean-ios-backups`**

- Scans `--ios-backups-dir` (default `~/Library/Application Support/MobileSync/Backup`)
  for per-device backup directories.
- Sorts by directory mtime; always keeps the `--ios-backups-keep` most recent
  (default 1) untouched, regardless of mode.
- Refuses to run if `--ios-backups-keep` is set below 1 (would delete all backups).

**11.12 `find-bundle-orphans`**

- Report-only (no `apply` action) — same caution as `find-orphans`.
- Reads each installed app's real `CFBundleIdentifier` from
  `/Applications/*.app/Contents/Info.plist` via `plistlib`, then does an **exact**
  match (not fuzzy/substring) against entries in `~/Library/Containers`,
  `~/Library/Preferences`, `~/Library/Saved Application State`, and
  `~/Library/Application Scripts`.
- This exists because those four locations are keyed by bundle identifier, not by
  app display name — the fuzzy substring match `find-orphans` uses against
  Application Support does not work there.
- Entries are filtered to bundle-ID-shaped names (`segment.segment...`, at least
  one dot) before matching, to exclude UUID-named containers and dotfiles that are
  never going to look like a real bundle ID.
- Known false-positive source: helper tools, browser extensions, and group
  containers often use a different (frequently Team-ID-prefixed) bundle ID than
  their parent app, so they appear as "orphans" even when legitimate. The tool
  logs this caveat and defers all deletion decisions to manual review.

**11.13 `chrome-cleanup` (multi-channel)**

- Generalized beyond Chrome Beta: the process name to detect/quit is a parameter
  (`--chrome-process-name`, default `Google Chrome Beta`), so pointing
  `--chrome-dir` at stable Chrome plus `--chrome-process-name "Google Chrome"`
  cleans the stable channel with no new task.
- Shared helpers `process_running(name)` / `close_app(name)` back both this task
  and `safari-cleanup`. Both use `pgrep -x` / `pkill -x` (exact executable-name
  match), **not** `-f` (command-line substring). `-f` would match helper and XPC
  processes and unrelated commands (e.g. `pgrep -f Safari` matches ~20 processes
  including `1Password for Safari` and the `com.apple.Safari.*` helpers), causing
  both false "still running" guards and — via `pkill` — collateral kills. `-x`
  matches only the browser process itself; macOS `pgrep -x` matches the full name
  (no 15-char `comm` truncation), so multi-word names like `Google Chrome Beta`
  work.

**11.14 `safari-cleanup`**

- Clears cache and per-site WebKit data only: `--safari-cache-dir`
  (`~/Library/Caches/com.apple.Safari`), `--safari-favicon-dir`
  (`~/Library/Safari/Favicon Cache`), `--safari-website-data-dir`
  (`~/Library/WebKit/com.apple.Safari/WebsiteData`).
- Deliberately does **not** touch `History.db`, `Bookmarks.plist`, or the shared
  `~/Library/Cookies/Cookies.binarycookies` (shared across all WebKit apps).
- Refuses to act while Safari is running unless `--kill-safari` is given; reuses
  `_clean_dir_contents` for each target, with the same `DEFAULT_CACHE_MIN_AGE_SECONDS`
  age guard as `clean-caches` (Safari's XPC helpers keep writing after the main
  app quits, so skip anything touched in the last few minutes).

**11.15 `find-launch-agents`**

- Report-only. Parses `~/Library/LaunchAgents/*.plist` (`--launch-agents-dir`) via
  `plistlib`, printing each `Label`, its `Program`/first `ProgramArguments` entry,
  `RunAtLoad`, and current loaded state (from `launchctl print gui/$UID/<label>`).
- Malformed plists (and valid plists whose root is not a dict) are logged and
  skipped, never fatal — one bad file can't abort the task or the run.

**11.16 `disable-login-item` / `disable-launch-agent`**

- Both call one `_disable_startup_item(label, mode, kind)` helper that runs
  `launchctl disable gui/$UID/<label>` — the identical, persistent, reversible
  mechanism for ServiceManagement login items and classic LaunchAgents.
- Never auto-acts: the user must name each label explicitly via repeatable
  `--login-item` / `--launch-agent` flags (like `archive-orphans` requires an
  explicit `--archive-folder` list). No labels given → "nothing to do".
- Reversal (`launchctl enable gui/$UID/<label>`) is printed in the success log.

---

**12. Data Model**

- `CommandResult`: normalized output for report commands.
- `ReportSection`: logical grouping of command results.
- No persistent data storage beyond optional report output files.

---

**13. CLI Design**

Primary parameters.

- `--mode {report,dry-run,apply}`
- `--task <task>` (repeatable)

Report parameters.

- `--report-out-dir`
- `--include-network`
- `--include-heavy`
- `--include-profiler`
- `--include-logs`
- `--timeout`
- `--max-chars`
- `--max-lines`

Brew parameters.

- `--brew-bin`
- `--brew-list-file`
- `--brew-cask-file`
- `--brew-update`
- `--brew-upgrade`
- `--brew-upgrade-cask`
- `--brew-autoremove`
- `--brew-cleanup`
- `--brew-doctor`
- `--brew-missing`
- `--brew-list`
- `--brew-cask-list`
- `--brew-untap`
- `--brew-fix-missing-casks`
- `--brew-fix-cask`

Orphan and archive parameters.

- `--app-support-dir`
- `--applications-dir`
- `--orphans-limit`
- `--archive-dir`
- `--archive-days`
- `--archive-folder`

Browser parameters.

- `--chrome-dir`
- `--kill-chrome`
- `--chrome-process-name`
- `--safari-cache-dir`
- `--safari-favicon-dir`
- `--safari-website-data-dir`
- `--kill-safari`

Startup-item parameters.

- `--launch-agents-dir`
- `--login-item` (repeatable)
- `--launch-agent` (repeatable)

Copy parameters.

- `--copy-src`
- `--copy-dst`

Cache, trash, logs, and iOS backup parameters.

- `--cache-dir`
- `--cache-min-age`
- `--trash-dir`
- `--logs-dir`
- `--logs-min-age`
- `--ios-backups-dir`
- `--ios-backups-keep`

---

**14. Safety and Security**

- All filesystem writes are gated behind `apply` mode.
- All deletions are explicit and constrained to validated paths.
- Home directory validation is enforced for user-writable targets.
- Brew binary path is validated and requires an absolute executable path.
- Chrome/Safari cleanup is scoped to expected profile/cache directories.
- Startup-item disabling uses `launchctl disable`, which is persistent but fully
  reversible via `launchctl enable gui/$UID/<label>` (printed in the success log).
  The tool never auto-disables — each label must be named explicitly.
- Network operations are opt-in.

---

**15. Error Handling**

- Command failures are logged with stderr excerpts.
- Report generator captures stderr and return codes for visibility.
- Exceptions in one task should not crash the entire run; failures are logged and the tool proceeds when safe.
- Timeouts are respected for long-running commands.

---

**16. Logging**

- Timestamped log lines for all actions.
- Dry-run logs use “would” language to indicate intended actions.
- Report generation logs output file paths.

---

**17. Report Output**

- Output files:
- `mac_maintenance_report_YYYYMMDD_HHMMSS.html`
- `mac_maintenance_report_YYYYMMDD_HHMMSS.css`
- Report UI features:
- Summary cards
- Table of contents
- Collapsible per-check output
- Search and status filters
- Copy command buttons

---

**18. Performance**

- Heavy scans are opt-in.
- Parallel execution is not used by default to preserve predictability.
- Truncation of large outputs prevents excessive report size.

---

**19. Testing Strategy**

- `pytest` suite in `tests/test_mac_maintenance.py` covers path validation, regex-based
  parsing (hardware model, login items, orphan skip-list), mode-gating (dry-run/report
  never write or delete), age-guarded content deletion (caches/trash/logs), iOS backup
  retention, bundle-ID extraction and matching, process detection, Safari/Chrome
  cleanup branching, LaunchAgent plist parsing, `launchctl disable` invocation
  (mocked — never run for real), and report generation.
- All process-control and `launchctl` calls are monkeypatched in tests; no test ever
  quits an app or disables a real startup item.
- Manual dry-run validation of each task.
- Manual report-only run of `find-bundle-orphans` / `find-launch-agents` against the
  real machine to sanity check output before acting.
- Report generation smoke test.

---

**20. Migration Plan**

- Keep legacy scripts in place during transition.
- Provide a new unified entrypoint for day-to-day use.
- Add deprecation notes in legacy scripts later if desired.

---

**21. Open Questions**

- Should the tool include a `--task all` shortcut?
- Should the Chrome cleanup target stable Chrome as well as Beta?
- Should report generation be the implicit default for `report` mode even when `--task` is omitted?
- Should we add a `--config` file to store defaults?

---

**22. Example Commands**

- Report only:
- `python3 mac-maintenance.py --mode report --task report-html --report-out-dir .`

- Dry-run brew cleanup and archive cleanup:
- `python3 mac-maintenance.py --mode dry-run --task brew-maintenance --task cleanup-archives --brew-cleanup --brew-list`

- Apply brew updates:
- `python3 mac-maintenance.py --mode apply --task brew-maintenance --brew-update --brew-upgrade`

- Apply archive cleanup:
- `python3 mac-maintenance.py --mode apply --task cleanup-archives --archive-dir ~/Desktop/Orphaned_App_Support_Archives`

- Dry-run Chrome cleanup:
- `python3 mac-maintenance.py --mode dry-run --task chrome-cleanup --chrome-dir "~/Library/Application Support/Google/Chrome Beta"`
