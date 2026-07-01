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

### Critique of the original plan (before implementation)

The original 2C sketch ("extend `find-orphans` to also scan Containers/Preferences/
Saved State/App Scripts, match the same way Application Support is matched today")
was flawed. `find-orphans`'s matching is **fuzzy substring on app display name**
(folder `"Slack"` vs app `"Slack.app"`). That breaks for the four new locations:
`~/Library/Preferences` files and `~/Library/Containers` dirs are named by **bundle
identifier** (`com.tinyspeck.slackmacgap.plist`), not display name. A substring
match would silently produce garbage — exactly the "looks fine, silently wrong"
bug class Track 1 was about eliminating. Fixed by redesigning 2C around real
`CFBundleIdentifier` extraction (see below) instead of implementing the original
plan as written.

### Bonus finds while implementing (same bug class as Track 1, missed in the original review)

- [x] **`DEFAULT_ORPHANS_SKIP_RE` had the exact Track 1 double-backslash regex bug**
  — `com\\.apple\\.` and `default\\.store` never matched real folder names, so
  `find-orphans` wasn't actually filtering out Apple-owned folders as intended.
  Fixed, plus a second latent bug in the same regex: the trailing `$` anchor forced
  a full-string match, so even with the backslash fixed, `com\.apple\.` (clearly a
  prefix) still couldn't match `com.apple.Safari` — needed `com\.apple\..*`.
  Regression test: `test_default_orphans_skip_re_matches_real_folder_names`.
- [x] **`human_size_kb` always showed GB** (1 KB → "0.00 GB") — fixed with KB/MB/GB
  thresholds, since cache/log entries are frequently small. This was deferred in
  Track 1 but became directly relevant once Track 2 started surfacing these sizes.

### 2A. Cache cleanup — ✅ DONE

- [x] `task_clean_caches()` — deletes immediate children of `--cache-dir` (default
  `~/Library/Caches`), skips anything modified within `--cache-min-age` seconds
  (default 300s) to avoid racing an app mid-write. Per-entry + total size reporting.
  Wired to `--task clean-caches`.

### 2B. Trash + Logs + iOS Backups — ✅ DONE

- [x] `task_empty_trash()` — `~/.Trash` (`--trash-dir`), no age guard (items are
  already user-deleted). `--task empty-trash`.
- [x] `task_clean_logs()` — `~/Library/Logs` (`--logs-dir`), same age-guard
  mechanics as caches via `--logs-min-age`. `--task clean-logs`.
- [x] `task_clean_ios_backups()` — `~/Library/Application Support/MobileSync/Backup`
  (`--ios-backups-dir`), sorts by mtime, always keeps `--ios-backups-keep` most
  recent (default 1), refuses to run if set below 1. `--task clean-ios-backups`.
- All three share a `_clean_dir_contents()` helper (cache/trash/logs are
  structurally identical: delete top-level entries, dry-run support, optional age
  guard) — avoided triplicating the same loop.

### 2C. Application leftovers — bundle-ID detection ✅ DONE, deletion deferred

- [x] `installed_bundle_ids()` — reads each `/Applications/*.app/Contents/Info.plist`
  via stdlib `plistlib`, returns `{CFBundleIdentifier: app_name}`. No shelling out.
- [x] `task_find_bundle_orphans()` — exact-match (not fuzzy) against
  `~/Library/Containers`, `~/Library/Preferences`, `~/Library/Saved Application State`,
  `~/Library/Application Scripts`. Filters to bundle-ID-shaped names (`segment.segment`,
  ≥1 dot) before matching, which excludes UUID-named containers and dotfiles.
  **Report-only** — same caution `find-orphans` already exercises today; no
  delete/archive action wired up yet.
- [x] Verified live against this machine (read-only): tightening the shape filter
  cut "potential orphan" counts roughly 25–30% (containers 420→309, preferences
  669→524, app-scripts 488→360) by removing UUID/dotfile noise. Residual noise is
  real and disclosed in the tool's own output: helper tools, browser extensions,
  and group containers often use a different (frequently Team-ID-prefixed) bundle
  ID than their parent app, so they show up as "orphans" even when legitimate —
  this is an inherent limit of bundle-ID-only matching, not a bug to chase further
  without building out a real signature database (out of scope for this tool).
- [ ] **Deferred**: wiring an `archive`/`delete` action on top of
  `find-bundle-orphans`'s output, mirroring how `archive-orphans` requires an
  explicit user-curated folder list rather than auto-deleting anything `find-orphans`
  surfaces. Do this only after living with the report output for a while and
  confirming the false-positive rate is tolerable for your own machine.

### 2D. Stretch goals (still open)

- [ ] Login items: add `--task disable-login-item <label>` (currently report-only)
- [ ] Launch agents: add `--task disable-launch-agent <label>`
- [ ] Browser history/cookies: extend beyond Chrome Beta to stable Chrome, Safari, Firefox
- [ ] Recent items: clear `NSRecentDocuments` plists
- [ ] 2C deletion wiring (see above)

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

## Re-run verdict — Track 2A/2B/2C-report complete

Confirmed by 27/27 passing tests, a live read-only `find-bundle-orphans` run
against this machine, and a CLI smoke test of `clean-caches`/`empty-trash`/
`clean-ios-backups` against a throwaway scratch directory under home (never
against real `~/Library`). CleanMyMac fitness moves meaningfully: caches, Trash,
and Logs cleanup (CMM's highest-volume disk-recovery actions) now exist with
dry-run-by-default safety. App-leftover detection is now bundle-ID-accurate
instead of fuzzy-matched, though still report-only.

## Recommended next action

1. **Live with `find-bundle-orphans` for a while** before wiring up deletion for
   it — the false-positive rate from helper-tool/Team-ID bundle IDs is real and
   disclosed; deleting based on it today would be premature.
2. **2D stretch goals** (login item / launch agent disable, multi-browser privacy,
   recent items) are the next clear chunk of CMM feature-parity work.
3. The three deferred Track 1C minor items (`run_brew` timeout typing,
   `time.time()` → `time.monotonic()` in copy-speed-test) are still just sitting
   there — low priority, fine to bundle into whatever PR touches those functions
   next rather than a dedicated pass.
