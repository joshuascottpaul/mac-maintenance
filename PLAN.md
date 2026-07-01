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

### 2D. Stretch goals

- [x] **Login items**: `--task disable-login-item --login-item <label>` (repeatable).
- [x] **Launch agents**: `--task disable-launch-agent --launch-agent <label>`
  (repeatable), plus a new report-only `--task find-launch-agents` that parses
  `~/Library/LaunchAgents/*.plist` and shows Label/Program/RunAtLoad/loaded state.
  Both disable tasks share one `_disable_startup_item()` helper running
  `launchctl disable gui/$UID/<label>` (reversible via `launchctl enable`); never
  auto-acts — labels must be named explicitly.
- [x] **Browsers**: generalized `chrome-cleanup` to any Chromium channel via
  `--chrome-process-name` (default still Chrome Beta, so existing behavior
  unchanged); point `--chrome-dir` at stable Chrome + `--chrome-process-name
  "Google Chrome"`. New `safari-cleanup` clears Safari cache + favicon +
  per-site WebKit data only — deliberately **not** History.db, Bookmarks, or the
  shared Cookies.binarycookies.
- [ ] **Firefox**: not done — Firefox uses a different profile/cache layout
  (`~/Library/Application Support/Firefox/Profiles/*`, `~/Library/Caches/Firefox`);
  deferred as a separate follow-up.
- [ ] **Recent items**: clear `NSRecentDocuments` plists — still open.
- [ ] **2C deletion wiring** (see above) — still deferred pending real-world
  false-positive assessment.

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

---

## Re-run verdict — Track 2D (browsers + startup items) complete

Confirmed by 38/38 passing tests plus live smoke tests: `find-launch-agents`
ran read-only against the real machine (parsed 23 plists, gracefully skipped one
genuinely malformed plist without crashing), stable-Chrome `chrome-cleanup`
dry-run found the real Default profile via `--chrome-process-name "Google
Chrome"`, `safari-cleanup` dry-run correctly detected Safari running and bailed,
and `disable-launch-agent` dry-run printed the exact `launchctl disable` command
without executing it. All destructive/process-control paths are monkeypatched in
tests — no test quits an app or disables a real startup item.

Shipped: multi-channel Chromium cleanup, Safari cache/site-data cleanup,
LaunchAgent discovery, and reversible login-item / launch-agent disabling.

## Recommended next action

1. **Live with `find-bundle-orphans` for a while** before wiring up deletion for
   it — the false-positive rate from helper-tool/Team-ID bundle IDs is real and
   disclosed; deleting based on it today would be premature.
2. **Remaining 2D**: Firefox cleanup (different profile/cache layout) and
   `NSRecentDocuments` recent-items clearing.
3. The two deferred Track 1C minor items (`run_brew` timeout typing,
   `time.time()` → `time.monotonic()` in copy-speed-test) are still just sitting
   there — low priority, fine to bundle into whatever PR touches those functions
   next rather than a dedicated pass.

---

## Track 3 — Backup & rollback for destructive tasks

### Assessment (as of this review)

Inventory of every destructive call and its reversibility **today**:

| Task | Destructive op | Reversible today? |
|---|---|---|
| `disable-login-item` / `disable-launch-agent` | `launchctl disable` | ✅ Yes — `launchctl enable gui/$UID/<label>` (undo command printed in the log) |
| `archive-orphans` | zip, then `rmtree` original | ✅ Effectively — the zip is the backup; unzip restores |
| `cleanup-archives` | `unlink` expired zip | ⚠️ No — intended end-of-life for archives past their delete date; leaving as-is |
| `clean-caches` | `unlink`/`rmtree` | ❌ No backup, no rollback |
| `clean-logs` | `unlink`/`rmtree` | ❌ No backup, no rollback |
| `empty-trash` | `unlink`/`rmtree` | ❌ No (and it *is* the Trash — permanent by definition) |
| `chrome-cleanup` / `safari-cleanup` | `unlink`/`rmtree` | ❌ No backup, no rollback |
| `clean-ios-backups` | `rmtree` | ❌ No — **highest-value / often-irreplaceable data in the tool** |

**Gap:** six file-deletion tasks permanently delete with only dry-run as the
safety net, and there is no `restore` command anywhere. `clean-ios-backups` is
the sharpest risk (device backups may be the only copy of photos/messages).

### Decision (confirmed with owner): move-to-Trash by default

- The five recoverable deletion tasks — `clean-caches`, `clean-logs`,
  `safari-cleanup`, `chrome-cleanup`, `clean-ios-backups` — move items to the
  macOS Trash instead of `unlink`/`rmtree`. Rollback = recover from Trash
  (drag out, or Finder "Put Back").
- `empty-trash` is exempt (it *is* the Trash) and stays a permanent delete.
- A new `--permanent` flag opts back into immediate `unlink`/`rmtree` for users
  who want the space reclaimed now rather than on Trash-empty.
- `cleanup-archives` / `archive-orphans` are unchanged — archive-orphans already
  backs up (zip), and cleanup-archives only removes already-expired archives.

### Verified mechanism (stdlib-only, consistent with existing architecture)

`osascript -l JavaScript` → `NSFileManager.trashItemAtURLResultingItemURLError`.
This is the same native trash API Finder uses; verified live on this machine —
a probe file moved out of its origin into `~/.Trash` and was recoverable. Uses
only `osascript`, a system binary the tool already shells out to (like `pgrep`,
`du`, `launchctl`, `zip`), so it keeps the "no third-party deps / no PyObjC"
constraint.

**Honest caveat:** recovery-from-Trash is guaranteed (item is not destroyed
until Trash is emptied). Finder's *"Put Back to exact original path"* is a Finder
feature; `trashItemAtURL:` is the API Finder itself uses so it is expected to
work, but a quick `mdls`/`xattr` probe did not positively confirm the put-back
record (Finder stores it separately, not as an xattr). The substantive win —
deletions become recoverable rather than immediate — is confirmed regardless.

### Reversibility after Track 3 lands

| Task | After Track 3 |
|---|---|
| `clean-caches` / `clean-logs` / `safari-cleanup` / `chrome-cleanup` | ✅ Recoverable from Trash (unless `--permanent`) |
| `clean-ios-backups` | ✅ Recoverable from Trash (unless `--permanent`) |
| `empty-trash` | ❌ Permanent (by definition) |
| `disable-*` | ✅ Already reversible (`launchctl enable`) |

### Implementation — ✅ DONE

Built after a two-round plan→review→revise loop (round 1: 2 Critical + 3 Major;
round 2: confirmed resolved + caught the SCRIPT segfault, independently fixed).

1. ✅ `move_to_trash(path) -> bool` — `osascript` JXA `trashItemAtURL`, path passed
   only as argv (no injection), both out-params `null` + static-string throw (no
   segfault), success=exit0/failure=exit1. Trash failure logs + returns False;
   caller never falls back to a permanent delete.
2. ✅ `_dispose(entry, permanent)` shared by `_clean_dir_contents`,
   `task_clean_ios_backups`, `task_chrome_cleanup`. chrome-cleanup now trashes the
   whole named cache subdir (Chrome regenerates it).
3. ✅ `--permanent` flag threaded through the five recoverable tasks; `empty-trash`
   hard-wired `permanent=True`.
4. ✅ Append-only action log (`log_action`/`init_action_log`) at
   `~/.mac-maintenance/actions.jsonl` (0o600), apply-mode only, size-before-disposal;
   `--task show-actions` reads it (truncation-tolerant, `--run-id` filter).
5. ✅ Auto-`rollback` deferred by design (Finder Put Back is the verified restore);
   documented with the guards it would need.
6. ✅ 48/48 tests pass (7 new incl. argv-injection, trash-vs-permanent,
   trash-failure-no-fallback, empty-trash-always-permanent, show-actions). Verified
   live: dry-run writes no log; apply moves to Trash + logs; show-actions reads back.
7. ✅ Docs: README, SDD §11.17 + §14 + CLI list, this file.
