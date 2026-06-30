# mac-maintenance — Fix & Feature Plan

Generated from code review. Two tracks: **Part 1** fixes correctness and quality of
what exists; **Part 2** closes the gap to a real CleanMyMac replacement.

---

## Track 1 — Correctness & Quality Fixes — ✅ DONE (see commit history)

All items below were fixed and verified with a passing `pytest tests/` run
(15/15, including 7 new regression tests). Detailed fix+test sequence and
verified line numbers: see the test plan this was executed from.

### 1A. Critical bugs (fix first — silent wrong output)

- [x] **Regex escaping — lines 628, 631, 750**
  - Extracted into testable `parse_ioreg_model()` / `parse_login_item_labels()` helpers
    and fixed the double-backslash escaping bug in both.
  - New tests assert against real `ioreg`/`launchctl` sample output.

- [x] **Test file loads wrong path — `tests/test_mac_maintenance.py:8`**
  - Now `Path(__file__).parent.parent / "mac-maintenance.py"`.

- [x] **`package.sh` copies wrong filename — lines 5, 8, 10, 21, 27**
  - All `mac_maintenance` → `mac-maintenance`. Verified end-to-end: ran
    `bash package.sh v0.1.1-test`, confirmed correct tarball name and contents.

- [x] **Hardcoded personal paths as CLI defaults**
  - `--copy-src`/`--copy-dst` now default to `""`; `task_copy_speed_test` logs an
    error and exits if either is unset, instead of silently resolving to cwd.

### 1B. Major bugs

- [x] **`validate_home_path` allows path traversal — `mac-maintenance.py:1356`**
  - Now uses `resolved.is_relative_to(home)`. New regression test covers the
    sibling-prefix case (`~evil` next to home dir).

- [x] **`task_archive_orphans` creates real dirs in dry-run**
  - `ensure_dir(archive_dir)` moved inside the `mode == MODE_APPLY` branch.

- [x] **Brew list files written in report mode**
  - `do_list`/`do_cask_list` now gated on `mode == MODE_APPLY` only.

- [x] **`do_fix_casks` ignores uninstall return code**
  - Now checks `uninstall_proc.returncode` and skips `install` (with a logged
    warning) if uninstall failed.

- [x] **`chrome-cleanup` swallows all errors silently**
  - Both except blocks now log the path and exception instead of `pass`.

- [x] **`release.yml` / `package.sh` tarball name mismatch**
  - Resolved as a side effect of the `package.sh` fix — verified the constructed
    download URL now matches the real tarball name. Also removed the dangling
    "see requirements.txt" line.

### 1C. Minor polish

- [x] **Tests create real dirs under `~/.mac_maintenance_test/`**
  - Added a `home_tmp_path` pytest fixture (tempfile under `Path.home()`, with
    teardown) — `validate_home_path` requires paths under home, so plain
    `tmp_path` doesn't work here. All affected tests now use it; leftover
    directories from old runs were also deleted.
- [ ] **`human_size_kb` always shows GB** — 1 KB renders as `0.00 GB`. Add KB / MB thresholds. (not done — low priority, deferred)
- [ ] **`run_brew` timeout typed `Optional[int]`** — rest of codebase uses `float`. (not done — deferred)
- [ ] **`task_copy_speed_test` uses `time.time()`** — should be `time.monotonic()`. (not done — deferred)

---

## Track 2 — CleanMyMac Feature Gaps

### Current fitness: ~25–30% of CMM feature surface

The tool is strong at Homebrew management and system health reporting. CMM's core
disk-recovery features (caches, logs, Trash) are entirely absent.

### 2A. Gap 1 — System cache cleanup (highest priority)

CMM's #1 disk-recovery action. Typically 2–10 GB on an active machine.

- [ ] Add `task_clean_caches()` function
  - Targets: `~/Library/Caches/*` (per-app cache dirs), optionally `/Library/Caches`
  - Dry-run: list each dir + size (use `du_kb`), total estimate
  - Apply: delete contents of each subdir (not the dir itself), log per-app bytes freed
  - Protect: skip dirs still being written to (check mtime < N minutes), skip any dir
    not owned by the current user
  - Wire to `--task clean-caches` flag

### 2B. Gap 2 — Trash + Logs + iOS Backups empty

Safe, bounded, typically 5–20 GB combined. Three separate tasks.

- [ ] `task_empty_trash()` — `~/.Trash`, with dry-run size report
- [ ] `task_clean_logs()` — `~/Library/Logs/*`, dry-run first
- [ ] `task_clean_ios_backups()` — `~/Library/Application Support/MobileSync/Backup/*`
  - Dry-run: list each backup, date, and size
  - Apply: require explicit `--keep-latest-n` arg (default 1) so the most recent backup
    is never auto-deleted
- [ ] Add `--task empty-trash`, `--task clean-logs`, `--task clean-ios-backups` flags

### 2C. Gap 3 — Complete application leftover cleanup

Currently `find-orphans` / `archive-orphans` cover only `~/Library/Application Support`.
Full CMM-equivalent coverage needs four more locations.

- [ ] Extend `task_find_orphans` to also scan:
  - `~/Library/Containers`
  - `~/Library/Preferences` (match `com.AppName.*` plist files)
  - `~/Library/Saved Application State`
  - `~/Library/Application Scripts`
- [ ] Extend `task_archive_orphans` / `task_cleanup_orphans` to act on the same set
- [ ] Update `--orphan-search-dirs` default list and README

### 2D. Stretch goals (post-gap-3)

- [ ] Login items: add `--task disable-login-item <label>` (currently report-only)
- [ ] Launch agents: add `--task disable-launch-agent <label>`
- [ ] Browser history/cookies: extend beyond Chrome Beta to stable Chrome, Safari, Firefox
- [ ] Recent items: clear `NSRecentDocuments` plists

---

## Re-run verdict — Track 1 complete

Confirmed by passing test suite (15/15) and a real `package.sh` dry-run:
- Hardware model and Mac chip family now parse correctly in reports
- ServiceManagement login items now list correctly
- `pytest tests/` passes against the actual repo file
- Packaging produces correctly-named tarballs with correct contents

Feature coverage is unchanged — Track 1 was reliability-only, no new features.
Fitness against CleanMyMac stays at ~25–30% of feature surface until Track 2 lands.
The tool's output is now trustworthy where it previously failed silently.

---

## Recommended next action

**Track 2 — CleanMyMac Feature Gaps** is next. Start with 2A (cache cleanup task) —
it's CMM's highest-volume disk-recovery action and the rest of the section spells
out the exact target directories and safety constraints (skip dirs mid-write, skip
non-owned dirs). 2B (Trash/Logs/iOS backups) is the natural follow-on since all
three are simple, bounded, apply-gated deletions.
