# Software Design Document (SDD)

**Project**: Unified macOS Maintenance Tool

**Location**: `/Users/jpaul/Desktop/mac_maintenance/mac_maintenance.py`

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

- Provide a single entrypoint: `mac_maintenance.py`.
- Support modes: `report`, `dry-run`, `apply`.
- Support tasks:
- `report-html`
- `brew-maintenance`
- `find-orphans`
- `archive-orphans`
- `cleanup-archives`
- `chrome-cleanup`
- `copy-speed-test`
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

- Main entrypoint: `mac_maintenance.py`
- Example invocation:
- `python3 mac_maintenance.py --mode report --task report-html --report-out-dir .`

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

Chrome parameters.

- `--chrome-dir`
- `--kill-chrome`

Copy parameters.

- `--copy-src`
- `--copy-dst`

---

**14. Safety and Security**

- All filesystem writes are gated behind `apply` mode.
- All deletions are explicit and constrained to validated paths.
- Home directory validation is enforced for user-writable targets.
- Brew binary path is validated and requires an absolute executable path.
- Chrome cleanup is scoped to expected profile directory.
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

- Manual dry-run validation of each task.
- Report generation smoke test.
- No automated tests yet; future work can add unit tests for utilities and report assembly.

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
- `python3 mac_maintenance.py --mode report --task report-html --report-out-dir .`

- Dry-run brew cleanup and archive cleanup:
- `python3 mac_maintenance.py --mode dry-run --task brew-maintenance --task cleanup-archives --brew-cleanup --brew-list`

- Apply brew updates:
- `python3 mac_maintenance.py --mode apply --task brew-maintenance --brew-update --brew-upgrade`

- Apply archive cleanup:
- `python3 mac_maintenance.py --mode apply --task cleanup-archives --archive-dir ~/Desktop/Orphaned_App_Support_Archives`

- Dry-run Chrome cleanup:
- `python3 mac_maintenance.py --mode dry-run --task chrome-cleanup --chrome-dir "~/Library/Application Support/Google/Chrome Beta"`
