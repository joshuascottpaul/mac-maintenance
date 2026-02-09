#!/usr/bin/env python3
"""
Unified macOS maintenance tool.
Modes:
  - report: read-only checks + optional HTML report generation
  - dry-run: show what would change without changing anything
  - apply: perform actions (only when explicitly requested via flags)
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import platform
import re
import shlex
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

MODE_REPORT = "report"
MODE_DRY_RUN = "dry-run"
MODE_APPLY = "apply"

TASK_REPORT = "report-html"
TASK_BREW = "brew-maintenance"
TASK_FIND_ORPHANS = "find-orphans"
TASK_ARCHIVE_ORPHANS = "archive-orphans"
TASK_CLEANUP_ARCHIVES = "cleanup-archives"
TASK_CHROME = "chrome-cleanup"
TASK_COPY = "copy-speed-test"

DEFAULT_ARCHIVE_DAYS = 90
DEFAULT_ORPHANS_LIMIT = 30

DEFAULT_ARCHIVE_FOLDERS = [
    "360Works",
    "Amazon Cloud Drive",
    "Alfred 2",
    "anythingllm-desktop",
    "AIR Music Technology",
    "Ableton",
    "Backup",
    "AIM",
    "Appfluence",
    "amazon-q",
]

DEFAULT_ORPHANS_SKIP_RE = re.compile(
    r"^(com\\.apple\\.|AddressBook|CallHistoryDB|CallHistoryTransactions|"
    r"CloudDocs|CrashReporter|FileProvider|Knowledge|SyncServices|"
    r"networkserviceproxy|icdd|default\\.store|Caches|Logs|MobileSync|"
    r"NotificationCenter|System Preferences|Automator|Dock|ControlCenter|"
    r"FaceTime|Mail|Music|iCloud|identityservicesd|locationaccessstored|"
    r"contactsd|accountsd|appplaceholdersyncd|homeenergyd|privatecloudcomputed|"
    r"syncdefaultsd|transparencyd|TrustedPersHelper|videosubscriptionsd|"
    r"stickersd|tipsd|DifferentialPrivacy|Animoji)$"
)

CHROME_CLEAN_DIRS = [
    "Service Worker",
    "IndexedDB",
    "File System",
    "Local Storage",
    "GPUCache",
    "WebStorage",
    "Application Cache",
    "Pepper Data",
    "Platform Notifications",
    "Session Storage",
]

DEFAULT_MISSING_CASK_APPS = ["Inkscape", "JupyterLab", "LosslessCut", "RsyncUI"]


@dataclass(frozen=True)
class CommandResult:
    title: str
    command: str
    duration_s: float
    returncode: Optional[int]
    stdout: str
    stderr: str
    skipped_reason: Optional[str] = None


@dataclass(frozen=True)
class ReportSection:
    title: str
    section_id: str
    results: List[CommandResult]


ANSI_ESCAPE_RE = re.compile(
    r"""
    (?:\x1B\[[0-?]*[ -/]*[@-~])      # CSI ... Cmd
  | (?:\x1B\][^\x07]*(?:\x07|\x1B\\)) # OSC ... BEL/ST
  | (?:\x1B[@-_])                    # 2-byte sequence
    """,
    re.VERBOSE,
)


CSS_TEXT = """\
:root {
  --bg: #0b1020;
  --panel: #121a33;
  --text: #e7ecff;
  --muted: #a9b4df;
  --border: rgba(231, 236, 255, 0.12);
  --ok: #2dd4bf;
  --warn: #fbbf24;
  --bad: #fb7185;
  --codebg: rgba(255, 255, 255, 0.04);
  --shadow: 0 20px 60px rgba(0,0,0,0.45);
}

* { box-sizing: border-box; }

body {
  margin: 0;
  padding: 32px 18px;
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI",
    Roboto, Helvetica, Arial, "Apple Color Emoji", "Segoe UI Emoji";
  background: radial-gradient(1200px 700px at 20% 0%, rgba(45, 212, 191, 0.12), transparent 60%),
    radial-gradient(900px 500px at 80% 20%, rgba(251, 191, 36, 0.10), transparent 60%),
    var(--bg);
  color: var(--text);
}

.wrap { max-width: 1100px; margin: 0 auto; }

header {
  border: 1px solid var(--border);
  background: rgba(18, 26, 51, 0.85);
  backdrop-filter: blur(6px);
  border-radius: 14px;
  padding: 18px 18px;
  box-shadow: var(--shadow);
}

h1 { margin: 0 0 6px; font-size: 22px; font-weight: 700; }
.meta { color: var(--muted); font-size: 13px; line-height: 1.5; }

.toolbar {
  margin-top: 12px;
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
}

.toolbar .left { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }

input[type="search"] {
  width: min(520px, 100%);
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: rgba(0, 0, 0, 0.18);
  color: var(--text);
  outline: none;
}
input[type="search"]::placeholder { color: rgba(169, 180, 223, 0.75); }

.pillbar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.toggle {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.02);
  color: var(--muted);
  font-size: 12px;
}
.toggle input { accent-color: var(--ok); }

.actions { display: flex; gap: 8px; flex-wrap: wrap; }
.btn {
  cursor: pointer;
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.02);
  color: var(--text);
  font-size: 12px;
}
.btn:hover { background: rgba(255, 255, 255, 0.05); }

.summary {
  margin-top: 14px;
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 10px;
}
@media (max-width: 980px) {
  .summary { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
@media (max-width: 520px) {
  .summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
.card {
  border: 1px solid var(--border);
  background: rgba(18, 26, 51, 0.65);
  border-radius: 14px;
  padding: 12px;
}
.card .k { color: var(--muted); font-size: 12px; }
.card .v { margin-top: 6px; font-size: 18px; font-weight: 800; letter-spacing: 0.2px; }
.card.ok .v { color: var(--ok); }
.card.warn .v { color: var(--warn); }
.card.bad .v { color: var(--bad); }

.toc {
  margin-top: 14px;
  border: 1px solid var(--border);
  background: rgba(18, 26, 51, 0.55);
  border-radius: 14px;
  padding: 12px;
}
.toc h2 { margin: 0 0 8px; font-size: 14px; }
.toc a { color: var(--text); text-decoration: none; }
.toc a:hover { text-decoration: underline; }
.tocgrid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px 10px;
}
@media (max-width: 720px) {
  .tocgrid { grid-template-columns: 1fr; }
}
.tocitem {
  display: flex;
  gap: 10px;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  border-radius: 12px;
  border: 1px solid rgba(231, 236, 255, 0.08);
  background: rgba(255, 255, 255, 0.02);
}
.tocitem.ok { border-color: rgba(45, 212, 191, 0.22); }
.tocitem.warn { border-color: rgba(251, 191, 36, 0.24); }
.tocitem.bad { border-color: rgba(251, 113, 133, 0.28); }

section {
  margin-top: 18px;
  border: 1px solid var(--border);
  background: rgba(18, 26, 51, 0.70);
  border-radius: 14px;
  overflow: hidden;
  box-shadow: 0 10px 40px rgba(0,0,0,0.30);
}
section[data-status="ok"] { border-color: rgba(45, 212, 191, 0.22); }
section[data-status="warn"] { border-color: rgba(251, 191, 36, 0.24); }
section[data-status="bad"] { border-color: rgba(251, 113, 133, 0.28); }
section[data-status="ok"] .sectionmeta { color: rgba(45, 212, 191, 0.85); }
section[data-status="warn"] .sectionmeta { color: rgba(251, 191, 36, 0.90); }
section[data-status="bad"] .sectionmeta { color: rgba(251, 113, 133, 0.92); }

section > h2 {
  margin: 0;
  padding: 12px 14px;
  font-size: 15px;
  font-weight: 700;
  border-bottom: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.03);
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
}

.sectionmeta { color: var(--muted); font-size: 12px; font-weight: 500; }

.block {
  padding: 14px;
  border-bottom: 1px solid var(--border);
}
.block:last-child { border-bottom: 0; }

.cmdblock {
  padding: 10px 12px;
  border: 1px solid rgba(231, 236, 255, 0.10);
  border-radius: 14px;
  background: rgba(0, 0, 0, 0.08);
  margin: 10px 0;
}
.cmdblock[open] { background: rgba(0, 0, 0, 0.12); }
.cmdblock[data-status="ok"] { border-color: rgba(45, 212, 191, 0.30); }
.cmdblock[data-status="warn"] { border-color: rgba(251, 191, 36, 0.35); }
.cmdblock[data-status="bad"] { border-color: rgba(251, 113, 133, 0.40); }
.cmdblock[data-status="ok"] { box-shadow: 0 0 0 1px rgba(45, 212, 191, 0.03) inset; }
.cmdblock[data-status="warn"] { box-shadow: 0 0 0 1px rgba(251, 191, 36, 0.04) inset; }
.cmdblock[data-status="bad"] { box-shadow: 0 0 0 1px rgba(251, 113, 133, 0.05) inset; }
.cmdblock > summary {
  cursor: pointer;
  list-style: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.cmdblock > summary::-webkit-details-marker { display:none; }
.sumleft { display: flex; flex-direction: column; gap: 6px; min-width: 260px; flex: 1; }
.sumright { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; justify-content: flex-end; }
.titleline { font-weight: 700; font-size: 13px; }
.cmdinline { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }

.cmdline {
  display: flex;
  gap: 10px;
  align-items: baseline;
  justify-content: space-between;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

code.cmd {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 12px;
  padding: 2px 8px;
  border: 1px solid var(--border);
  background: var(--codebg);
  border-radius: 999px;
  word-break: break-word;
}
.cmd--summary { opacity: 0.95; }

.copy {
  cursor: pointer;
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.02);
  color: var(--muted);
}
.copy:hover { background: rgba(255, 255, 255, 0.05); color: var(--text); }

.badges { display: flex; gap: 8px; flex-wrap: wrap; }
.badge {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid var(--border);
  color: var(--muted);
  background: rgba(255, 255, 255, 0.02);
}
.badge.ok { border-color: rgba(45, 212, 191, 0.35); color: var(--ok); }
.badge.warn { border-color: rgba(251, 191, 36, 0.35); color: var(--warn); }
.badge.bad { border-color: rgba(251, 113, 133, 0.35); color: var(--bad); }

pre {
  margin: 0;
  padding: 12px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: rgba(0, 0, 0, 0.20);
  overflow: auto;
  line-height: 1.45;
  font-size: 12px;
  color: var(--text);
  white-space: pre-wrap;
  word-break: break-word;
}

.subhead { margin: 10px 0 6px; color: var(--muted); font-size: 12px; }
footer { margin: 18px 2px 0; color: var(--muted); font-size: 12px; }

.hide { display: none !important; }

/* Modal help dialog */
.modal {
  position: fixed;
  inset: 0;
  display: none;
  place-items: center;
  padding: 18px;
  background: rgba(0, 0, 0, 0.55);
  backdrop-filter: blur(2px);
  z-index: 1000;
}
.modal.open { display: grid; }
.dialog {
  width: min(980px, 100%);
  max-height: min(80vh, 900px);
  overflow: auto;
  border-radius: 16px;
  border: 1px solid var(--border);
  background: rgba(18, 26, 51, 0.92);
  box-shadow: var(--shadow);
}
.dialoghead {
  position: sticky;
  top: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
  background: rgba(18, 26, 51, 0.97);
}
.dialoghead h3 { margin: 0; font-size: 14px; }
.dialogbody { padding: 12px 14px 14px; }
.kbd { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
"""


# ------------------------
# Core utilities
# ------------------------

def log(msg: str) -> None:
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")


def _strip_ansi(text: str) -> str:
    return ANSI_ESCAPE_RE.sub("", text or "")


def _truncate_text(text: str, max_chars: int, max_lines: int) -> Tuple[str, bool]:
    if not text:
        return "", False
    truncated = False
    lines = text.splitlines()
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        truncated = True
    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars]
        truncated = True
    return text, truncated


def _ensure_path_prefix(env: dict) -> dict:
    path = env.get("PATH", "")
    prefix = "/usr/sbin:/sbin"
    if prefix not in path:
        env["PATH"] = f"{prefix}:{path}" if path else prefix
    return env


def run_command(
    title: str,
    command: str,
    *,
    timeout_s: float,
    max_chars: int,
    max_lines: int,
    skip_reason: Optional[str] = None,
) -> CommandResult:
    if skip_reason:
        return CommandResult(
            title=title,
            command=command,
            duration_s=0.0,
            returncode=None,
            stdout=f"Skipped: {skip_reason}",
            stderr="",
            skipped_reason=skip_reason,
        )

    start = time.monotonic()
    try:
        env = _ensure_path_prefix(dict(os.environ))
        proc = subprocess.run(
            command,
            shell=True,
            text=True,
            capture_output=True,
            timeout=timeout_s,
            env=env,
        )
        duration_s = time.monotonic() - start
        out, out_trunc = _truncate_text(_strip_ansi(proc.stdout), max_chars=max_chars, max_lines=max_lines)
        err, err_trunc = _truncate_text(_strip_ansi(proc.stderr), max_chars=max_chars, max_lines=max_lines)
        if out_trunc:
            out += "\n\n[output truncated]"
        if err_trunc:
            err += "\n\n[stderr truncated]"
        return CommandResult(
            title=title,
            command=command,
            duration_s=duration_s,
            returncode=proc.returncode,
            stdout=out,
            stderr=err,
        )
    except subprocess.TimeoutExpired as e:
        duration_s = time.monotonic() - start
        stdout = (e.stdout or "")
        stderr = (e.stderr or "")
        stdout, _ = _truncate_text(_strip_ansi(stdout), max_chars=max_chars, max_lines=max_lines)
        stderr, _ = _truncate_text(_strip_ansi(stderr), max_chars=max_chars, max_lines=max_lines)
        if stdout:
            stdout += "\n\n[command timed out]"
        else:
            stdout = "[command timed out]"
        if stderr:
            stderr += "\n\n[command timed out]"
        return CommandResult(
            title=title,
            command=command,
            duration_s=duration_s,
            returncode=None,
            stdout=stdout,
            stderr=stderr,
        )
    except Exception as e:
        duration_s = time.monotonic() - start
        return CommandResult(
            title=title,
            command=command,
            duration_s=duration_s,
            returncode=None,
            stdout="",
            stderr=f"[exception] {type(e).__name__}: {e}",
        )


# ------------------------
# HTML report generation
# ------------------------

def badge_for_result(result: CommandResult) -> Tuple[str, str]:
    if result.skipped_reason:
        return "warn", "SKIPPED"
    if result.returncode == 0:
        return "ok", "OK"
    if result.returncode is None:
        if (result.stderr or "").startswith("[exception]"):
            return "bad", "EXC"
        return "warn", "TIMEOUT"

    if result.returncode in (126, 127):
        return "warn", "MISSING"

    err = (result.stderr or "").lower()
    if any(
        s in err
        for s in (
            "operation not permitted",
            "not authorized",
            "permission denied",
            "requires full disk access",
        )
    ):
        return "warn", f"RC={result.returncode}"

    if result.returncode == 1:
        return "warn", "RC=1"

    return "bad", f"RC={result.returncode}"


def _slugify(text: str) -> str:
    keep: List[str] = []
    last_dash = False
    for ch in text.lower():
        if ch.isalnum():
            keep.append(ch)
            last_dash = False
        elif not last_dash:
            keep.append("-")
            last_dash = True
    slug = "".join(keep).strip("-")
    return slug or "section"


def _format_section_meta(results: List[CommandResult]) -> str:
    ok = sum(1 for r in results if badge_for_result(r)[0] == "ok")
    warn = sum(1 for r in results if badge_for_result(r)[0] == "warn")
    bad = sum(1 for r in results if badge_for_result(r)[0] == "bad")
    return f"{len(results)} checks • {ok} ok • {warn} warn • {bad} bad"


def _section_status(results: List[CommandResult]) -> str:
    classes = [badge_for_result(r)[0] for r in results]
    if "bad" in classes:
        return "bad"
    if "warn" in classes:
        return "warn"
    return "ok"


def _run_argv(argv: List[str], *, timeout_s: float) -> Tuple[float, int, str, str]:
    start = time.monotonic()
    env = _ensure_path_prefix(dict(os.environ))
    proc = subprocess.run(argv, text=True, capture_output=True, timeout=timeout_s, env=env)
    duration_s = time.monotonic() - start
    return duration_s, proc.returncode, _strip_ansi(proc.stdout), _strip_ansi(proc.stderr)


def hardware_quick_summary_result(*, timeout_s: float, max_chars: int, max_lines: int) -> CommandResult:
    title = "Hardware quick summary"
    cmd = "ioreg -rd1 -c IOPlatformExpertDevice; system_profiler SPHardwareDataType -json"
    stdout_parts: List[str] = []
    stderr_parts: List[str] = []
    duration_total = 0.0
    rc = 0

    try:
        d1, rc1, out1, err1 = _run_argv(
            ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"], timeout_s=max(5.0, timeout_s)
        )
        duration_total += d1
        rc = rc1 if rc1 != 0 else rc
        if err1.strip():
            stderr_parts.append(f"[ioreg stderr]\n{err1.strip()}")

        model = None
        model_number = None
        if out1:
            m = re.search(r'"model"\\s*=\\s*<"([^"]+)"', out1)
            if m:
                model = m.group(1).strip()
            m2 = re.search(r'"model-number"\\s*=\\s*<([0-9A-Fa-f]+)>', out1)
            if m2:
                hex_bytes = m2.group(1)
                try:
                    decoded = bytes.fromhex(hex_bytes).decode("utf-8", errors="ignore").strip("\x00").strip()
                    if decoded:
                        model_number = decoded
                except Exception:
                    pass

        d2, rc2, out2, err2 = _run_argv(
            ["system_profiler", "SPHardwareDataType", "-json"], timeout_s=max(10.0, timeout_s)
        )
        duration_total += d2
        rc = rc2 if rc2 != 0 else rc
        if err2.strip():
            stderr_parts.append(f"[system_profiler stderr]\n{err2.strip()}")

        chip = None
        memory = None
        cores = None
        firmware = None
        os_loader = None
        sp_model_number = None

        if out2.strip():
            try:
                data = json.loads(out2)
                entries = data.get("SPHardwareDataType") or []
                entry = entries[0] if entries else {}
                chip = entry.get("chip_type")
                memory = entry.get("physical_memory")
                firmware = entry.get("boot_rom_version")
                os_loader = entry.get("os_loader_version")
                sp_model_number = entry.get("model_number")
                np = entry.get("number_processors") or ""
                if isinstance(np, str) and np.startswith("proc "):
                    parts = np.removeprefix("proc ").split(":")
                    if len(parts) == 3 and all(p.isdigit() for p in parts):
                        total, perf, eff = parts
                        cores = f"{total} ({perf}P+{eff}E)"
            except Exception as e:
                stderr_parts.append(f"[system_profiler parse]\n{type(e).__name__}: {e}")

        if model:
            stdout_parts.append(f"Model Identifier: {model}")

        if sp_model_number:
            stdout_parts.append(f"Model Number: {sp_model_number}")
        elif model_number:
            stdout_parts.append(f"Model Number: {model_number}")

        if chip:
            stdout_parts.append(f"Chip: {chip}")
        if cores:
            stdout_parts.append(f"Cores: {cores}")
        if memory:
            stdout_parts.append(f"Memory: {memory}")
        if firmware:
            stdout_parts.append(f"Firmware: {firmware}")
        if os_loader:
            stdout_parts.append(f"OS Loader: {os_loader}")

        out = "\n".join(stdout_parts).strip()
        if not out:
            out = "(no output)"
            if not stderr_parts:
                stderr_parts.append("No data returned from ioreg/system_profiler.")
            rc = rc or 1

        out, out_trunc = _truncate_text(out, max_chars=max_chars, max_lines=max_lines)
        err = "\n\n".join(stderr_parts).strip()
        err, err_trunc = _truncate_text(err, max_chars=max_chars, max_lines=max_lines)
        if out_trunc:
            out += "\n\n[output truncated]"
        if err_trunc:
            err += "\n\n[stderr truncated]"

        return CommandResult(
            title=title,
            command=cmd,
            duration_s=duration_total,
            returncode=0 if rc == 0 else rc,
            stdout=out,
            stderr=err,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(
            title=title,
            command=cmd,
            duration_s=duration_total,
            returncode=None,
            stdout="[command timed out]",
            stderr="",
        )
    except Exception as e:
        return CommandResult(
            title=title,
            command=cmd,
            duration_s=duration_total,
            returncode=None,
            stdout="",
            stderr=f"[exception] {type(e).__name__}: {e}",
        )


def login_items_quick_result(*, timeout_s: float, max_chars: int, max_lines: int) -> CommandResult:
    title = "Login items (ServiceManagement)"
    uid = os.getuid()
    cmd = "launchctl print gui/$UID + per-item launchctl print"
    duration_total = 0.0
    stderr_parts: List[str] = []

    try:
        d0, rc0, out0, err0 = _run_argv(["launchctl", "print", f"gui/{uid}"], timeout_s=max(10.0, timeout_s))
        duration_total += d0
        if err0.strip():
            stderr_parts.append(err0.strip())

        labels = sorted(set(re.findall(r"\\b[A-Za-z0-9_.-]+\\.loginitem\\b", out0)))
        labels = [l for l in labels if not l.startswith("com.apple.")]

        if not labels:
            out = "No ServiceManagement login items found via launchctl."
            out, out_trunc = _truncate_text(out, max_chars=max_chars, max_lines=max_lines)
            err = "\n".join(stderr_parts).strip()
            err, err_trunc = _truncate_text(err, max_chars=max_chars, max_lines=max_lines)
            if out_trunc:
                out += "\n\n[output truncated]"
            if err_trunc:
                err += "\n\n[stderr truncated]"
            return CommandResult(
                title=title,
                command=cmd,
                duration_s=duration_total,
                returncode=0 if rc0 == 0 else rc0,
                stdout=out,
                stderr=err,
            )

        blocks: List[str] = []
        wanted_prefixes = (
            "state = ",
            "path = ",
            "program identifier = ",
            "parent bundle identifier = ",
            "parent bundle version = ",
            "BTM uuid = ",
            "last exit code = ",
        )

        for label in labels[:50]:
            d1, _rc1, out1, err1 = _run_argv(
                ["launchctl", "print", f"gui/{uid}/{label}"], timeout_s=max(5.0, timeout_s)
            )
            duration_total += d1
            if err1.strip():
                stderr_parts.append(f"[{label} stderr]\n{err1.strip()}")

            lines: List[str] = []
            seen: set[str] = set()
            for line in out1.splitlines():
                stripped = line.strip()
                if any(stripped.startswith(p) for p in wanted_prefixes):
                    if stripped not in seen:
                        seen.add(stripped)
                        lines.append(stripped)

            if not lines:
                lines = ["(no details)"]

            blocks.append("\n".join([label] + [f"  {ln}" for ln in lines]))

        out = "\n\n".join(blocks)
        out, out_trunc = _truncate_text(out, max_chars=max_chars, max_lines=max_lines)
        err = "\n\n".join(stderr_parts).strip()
        err, err_trunc = _truncate_text(err, max_chars=max_chars, max_lines=max_lines)
        if out_trunc:
            out += "\n\n[output truncated]"
        if err_trunc:
            err += "\n\n[stderr truncated]"

        return CommandResult(
            title=title,
            command=cmd,
            duration_s=duration_total,
            returncode=0,
            stdout=out,
            stderr=err,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(
            title=title,
            command=cmd,
            duration_s=duration_total,
            returncode=None,
            stdout="[command timed out]",
            stderr="",
        )
    except Exception as e:
        return CommandResult(
            title=title,
            command=cmd,
            duration_s=duration_total,
            returncode=None,
            stdout="",
            stderr=f"[exception] {type(e).__name__}: {e}",
        )


def render_results_section(section: ReportSection) -> str:
    blocks: List[str] = []
    for r in section.results:
        badge_class, badge_text = badge_for_result(r)
        badges = [
            f'<span class="badge {badge_class}">{html.escape(badge_text)}</span>',
            f'<span class="badge">{html.escape(f"{r.duration_s:.2f}s")}</span>',
        ]
        if r.skipped_reason:
            badges.append(f'<span class="badge warn">{html.escape(r.skipped_reason)}</span>')

        default_open = badge_class != "ok"
        data_tags = [badge_class]
        if r.skipped_reason:
            data_tags.append("skipped")
        if badge_text == "TIMEOUT":
            data_tags.append("timeout")
        if badge_text == "EXC":
            data_tags.append("exc")
        if badge_text == "MISSING":
            data_tags.append("missing")

        blocks.append(
            "\n".join(
                [
                    '<div class="block">',
                    f'  <details class="cmdblock" data-status="{html.escape(badge_class)}" data-tags="{html.escape(" ".join(data_tags))}" {"open" if default_open else ""}>',
                    "    <summary>",
                    '      <div class="sumleft">',
                    f'        <div class="titleline">{html.escape(r.title)}</div>',
                    '        <div class="cmdinline">',
                    f'          <code class="cmd cmd--summary">{html.escape(r.command)}</code>',
                    f'          <button class="copy" type="button" data-copy="{html.escape(r.command)}">Copy</button>',
                    "        </div>",
                    "      </div>",
                    '      <div class="sumright">',
                    f'        <div class="badges">{"".join(badges)}</div>',
                    "      </div>",
                    "    </summary>",
                    f'    <pre>{html.escape(r.stdout) if r.stdout else "(no output)"}</pre>',
                    (
                        f'    <div class="subhead">stderr</div>\n    <pre>{html.escape(r.stderr)}</pre>'
                        if r.stderr
                        else ""
                    ),
                    "  </details>",
                    "</div>",
                ]
            )
        )

    return "\n".join(
        [
            f'<section id="{html.escape(section.section_id)}" data-status="{html.escape(_section_status(section.results))}">',
            "  <h2>",
            f"    <span>{html.escape(section.title)}</span>",
            f"    <span class=\"sectionmeta\">{html.escape(_format_section_meta(section.results))}</span>",
            "  </h2>",
            "\n".join(blocks),
            "</section>",
        ]
    )


def generate_report(
    *,
    out_dir: Path,
    include_network: bool,
    include_heavy: bool,
    include_profiler: bool,
    include_logs: bool,
    timeout: float,
    max_chars: int,
    max_lines: int,
) -> Path:
    now = dt.datetime.now().astimezone()
    stamp = now.strftime("%Y%m%d_%H%M%S")
    host = socket.gethostname()
    home = Path.home()
    home_q = shlex.quote(str(home))
    out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir / f"mac_maintenance_report_{stamp}"
    html_path = base.with_suffix(".html")
    css_path = base.with_suffix(".css")

    def do(title: str, command: str, *, timeout_s: Optional[float] = None, skip_reason: str = ""):
        return run_command(
            title,
            command,
            timeout_s=(timeout_s if timeout_s is not None else timeout),
            max_chars=max_chars,
            max_lines=max_lines,
            skip_reason=skip_reason or None,
        )

    brew_path = shutil.which("brew") or ""
    has_brew = bool(brew_path)

    sections: List[ReportSection] = []

    sections.append(
        ReportSection(
            "System",
            _slugify("System"),
            [
                do("Kernel and architecture", "uname -a"),
                do("macOS version", "sw_vers"),
                do("Uptime", "uptime"),
                hardware_quick_summary_result(
                    timeout_s=max(timeout, 15.0),
                    max_chars=max_chars,
                    max_lines=max_lines,
                ),
                do(
                    "Hardware summary (detailed; system_profiler)",
                    "system_profiler SPHardwareDataType -detailLevel mini",
                    skip_reason="" if include_profiler else "Use --include-profiler",
                    timeout_s=max(timeout, 60.0),
                ),
                do(
                    "Software summary (detailed; system_profiler)",
                    "system_profiler SPSoftwareDataType -detailLevel mini",
                    skip_reason="" if include_profiler else "Use --include-profiler",
                    timeout_s=max(timeout, 60.0),
                ),
            ],
        )
    )

    sections.append(
        ReportSection(
            "Disk & Storage",
            _slugify("Disk & Storage"),
            [
                do("Filesystem free space", "df -h"),
                do(
                    "Largest directories in home (top 30)",
                    f"du -hd 1 {home_q} 2>/dev/null | sort -h | tail -n 30",
                    skip_reason="" if include_heavy else "Use --include-heavy",
                    timeout_s=max(timeout, 60.0),
                ),
                do(
                    "Large files in home (>1GiB, first 200)",
                    f"find {home_q} -type f -size +1G -print 2>/dev/null | head -n 200",
                    skip_reason="" if include_heavy else "Use --include-heavy",
                    timeout_s=max(timeout, 60.0),
                ),
                do(
                    "Trash size",
                    f"du -sh {shlex.quote(str(home / '.Trash'))} 2>/dev/null || echo \"No ~/.Trash\"",
                ),
            ],
        )
    )

    if has_brew:
        sections.append(
            ReportSection(
                "Homebrew",
                _slugify("Homebrew"),
                [
                    do("Brew path", "command -v brew"),
                    do("Brew version", "brew --version"),
                    do("Brew config", "brew config"),
                    do(
                        "Outdated formulae/casks (may be inaccurate without brew update)",
                        "brew outdated --verbose",
                        timeout_s=max(timeout, 60.0),
                    ),
                    do(
                        "brew update (network)",
                        "brew update",
                        skip_reason="" if include_network else "Use --include-network",
                        timeout_s=max(timeout, 120.0),
                    ),
                ],
            )
        )
    else:
        sections.append(
            ReportSection(
                "Homebrew",
                _slugify("Homebrew"),
                [
                    do(
                        "Homebrew not found",
                        "command -v brew",
                        skip_reason="Not installed",
                    )
                ],
            )
        )

    sections.append(
        ReportSection(
            "Software Updates",
            _slugify("Software Updates"),
            [
                do(
                    "Available macOS updates (network)",
                    "softwareupdate -l",
                    skip_reason="" if include_network else "Use --include-network",
                    timeout_s=max(timeout, 120.0),
                )
            ],
        )
    )

    sections.append(
        ReportSection(
            "Startup & Background Items",
            _slugify("Startup & Background Items"),
            [
                login_items_quick_result(
                    timeout_s=max(timeout, 15.0),
                    max_chars=max_chars,
                    max_lines=max_lines,
                ),
                do(
                    "User LaunchAgents",
                    f"ls -1 {shlex.quote(str(home / 'Library' / 'LaunchAgents'))} 2>/dev/null || true",
                ),
                do("System LaunchAgents", "ls -1 /Library/LaunchAgents 2>/dev/null || true"),
                do("System LaunchDaemons", "ls -1 /Library/LaunchDaemons 2>/dev/null || true"),
                do("Loaded launchd jobs (first 60)", "launchctl list | head -n 60"),
            ],
        )
    )

    sections.append(
        ReportSection(
            "Security",
            _slugify("Security"),
            [
                do("FileVault status", "fdesetup status"),
                do("Gatekeeper status", "spctl --status"),
                do(
                    "Firewall status (0=off,1=on,2=on+stealth)",
                    "defaults read /Library/Preferences/com.apple.alf globalstate 2>/dev/null || echo \"Unavailable\"",
                ),
                do(
                    "Quarantine events (last 7 days, first 50)",
                    "log show --last 7d --predicate 'eventMessage contains[c] \"Gatekeeper\"' --style compact 2>/dev/null | head -n 50",
                    skip_reason="" if include_logs else "Use --include-logs",
                    timeout_s=max(timeout, 60.0),
                ),
            ],
        )
    )

    sections.append(
        ReportSection(
            "Backups (Time Machine)",
            _slugify("Backups (Time Machine)"),
            [
                do("Time Machine status", "tmutil status 2>/dev/null || echo \"tmutil not available\""),
                do(
                    "Time Machine destinations",
                    "tmutil destinationinfo 2>/dev/null || echo \"No destinations (or permission required)\"",
                    timeout_s=max(timeout, 60.0),
                ),
                do(
                    "Most recent backups (first 30)",
                    "tmutil listbackups 2>/dev/null | tail -n 30 || echo \"No backups listed\"",
                    timeout_s=max(timeout, 60.0),
                ),
            ],
        )
    )

    sections.append(
        ReportSection(
            "Battery & Power",
            _slugify("Battery & Power"),
            [
                do("Battery summary", "pmset -g batt 2>/dev/null || echo \"No battery\""),
                do(
                    "Power details (system_profiler)",
                    "system_profiler SPPowerDataType -detailLevel mini 2>/dev/null || echo \"Unavailable\"",
                    skip_reason="" if include_profiler else "Use --include-profiler",
                    timeout_s=max(timeout, 60.0),
                ),
            ],
        )
    )

    sections.append(
        ReportSection(
            "Logs (Quick Checks)",
            _slugify("Logs (Quick Checks)"),
            [
                do(
                    "Recent system errors (last 1h, tail 200)",
                    "log show --last 1h --predicate '(eventMessage CONTAINS[c] \"error\") OR (eventMessage CONTAINS[c] \"failed\")' --style compact 2>/dev/null | tail -n 200",
                    skip_reason="" if include_logs else "Use --include-logs",
                    timeout_s=max(timeout, 60.0),
                )
            ],
        )
    )

    all_results: List[CommandResult] = [r for s in sections for r in s.results]
    count_ok = sum(1 for r in all_results if badge_for_result(r)[0] == "ok")
    count_warn = sum(1 for r in all_results if badge_for_result(r)[0] == "warn")
    count_bad = sum(1 for r in all_results if badge_for_result(r)[0] == "bad")
    count_skipped = sum(1 for r in all_results if r.skipped_reason)
    total_runtime = sum(r.duration_s for r in all_results)

    actions_not_run = "\n".join(
        [
            "These are common maintenance actions that this report script does NOT run automatically:",
            "",
            "- Install macOS updates:  sudo softwareupdate -ia --verbose",
            "- Install + reboot:       sudo softwareupdate -iaR --verbose",
            "- Upgrade Homebrew:       brew upgrade",
            "- Cleanup Homebrew:       brew cleanup -s",
            "- Empty Trash:            rm -rf ~/.Trash/*",
            "- Reboot:                 sudo shutdown -r now",
            "",
            "Run them manually if/when you want to perform changes.",
        ]
    )

    toc_items = "\n".join(
        [
            f'<div class="tocitem {_section_status(s.results)}">'
            f'<a href="#{html.escape(s.section_id)}">{html.escape(s.title)}</a>'
            f'<span class="badge">{html.escape(_format_section_meta(s.results))}</span>'
            "</div>"
            for s in sections
        ]
    )

    sections_html = "\n".join(render_results_section(s) for s in sections)

    js = r"""
(() => {
  const $ = (sel, root=document) => root.querySelector(sel);
  const $$ = (sel, root=document) => Array.from(root.querySelectorAll(sel));

  const search = $('#search');
  const toggles = {
    ok: $('#toggle-ok'),
    warn: $('#toggle-warn'),
    bad: $('#toggle-bad'),
    skipped: $('#toggle-skipped'),
  };

  function matchesText(el, query) {
    if (!query) return true;
    const hay = (el.getAttribute('data-haystack') || '').toLowerCase();
    return hay.includes(query);
  }

  function matchesToggles(el) {
    const status = el.getAttribute('data-status') || '';
    const tags = (el.getAttribute('data-tags') || '').split(/\s+/).filter(Boolean);
    if (status === 'ok' && !toggles.ok.checked) return false;
    if (status === 'warn' && !toggles.warn.checked) return false;
    if (status === 'bad' && !toggles.bad.checked) return false;
    if (tags.includes('skipped') && !toggles.skipped.checked) return false;
    return true;
  }

  function applyFilters() {
    const q = (search.value || '').trim().toLowerCase();
    const blocks = $$('.cmdblock');
    for (const b of blocks) {
      const ok = matchesToggles(b) && matchesText(b, q);
      b.classList.toggle('hide', !ok);
    }
  }

  function wireCopyButtons() {
    for (const btn of $$('.copy')) {
      btn.addEventListener('click', async (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        const text = btn.getAttribute('data-copy') || '';
        try {
          await navigator.clipboard.writeText(text);
          btn.textContent = 'Copied';
          setTimeout(() => (btn.textContent = 'Copy'), 900);
        } catch (_) {
          btn.textContent = 'Failed';
          setTimeout(() => (btn.textContent = 'Copy'), 900);
        }
      });
    }
  }

  function addHaystacks() {
    for (const b of $$('.cmdblock')) {
      const title = (b.querySelector('.titleline')?.textContent || '');
      const cmd = (b.querySelector('code.cmd')?.textContent || '');
      b.setAttribute('data-haystack', `${title}\n${cmd}`.toLowerCase());
    }
  }

  $('#expand-all')?.addEventListener('click', () => $$('.cmdblock').forEach(d => d.open = true));
  $('#collapse-all')?.addEventListener('click', () => $$('.cmdblock').forEach(d => d.open = false));

  const helpBtn = $('#help-btn');
  const helpModal = $('#help-modal');
  const helpClose = $('#help-close');

  function openHelp() {
    helpModal?.classList.add('open');
  }
  function closeHelp() {
    helpModal?.classList.remove('open');
  }

  helpBtn?.addEventListener('click', openHelp);
  helpClose?.addEventListener('click', closeHelp);
  helpModal?.addEventListener('click', (e) => {
    if (e.target === helpModal) closeHelp();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeHelp();
  });

  search?.addEventListener('input', applyFilters);
  Object.values(toggles).forEach(t => t?.addEventListener('change', applyFilters));

  addHaystacks();
  wireCopyButtons();
  applyFilters();
})();
"""

    page = "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '  <meta charset="utf-8" />',
            '  <meta name="viewport" content="width=device-width, initial-scale=1" />',
            f"  <title>{html.escape('macOS Maintenance Report')}</title>",
            f'  <link rel="stylesheet" href="{html.escape(css_path.name)}" />',
            "</head>",
            "<body>",
            '  <div class="wrap">',
            "    <header>",
            f"      <h1>macOS Maintenance Report</h1>",
            '      <div class="meta">',
            f"        <div><b>Host:</b> {html.escape(host)}</div>",
            f"        <div><b>Generated:</b> {html.escape(now.isoformat())}</div>",
            f"        <div><b>User:</b> {html.escape(os.getenv('USER', ''))}</div>",
            f"        <div><b>Python:</b> {html.escape(platform.python_version())}</div>",
            "      </div>",
            '      <div class="toolbar">',
            '        <div class="left">',
            '          <input id="search" type="search" placeholder="Filter by check name or command…" autocomplete="off" />',
            '          <div class="pillbar">',
            '            <label class="toggle"><input id="toggle-ok" type="checkbox" checked /> OK</label>',
            '            <label class="toggle"><input id="toggle-warn" type="checkbox" checked /> WARN</label>',
            '            <label class="toggle"><input id="toggle-bad" type="checkbox" checked /> BAD</label>',
            '            <label class="toggle"><input id="toggle-skipped" type="checkbox" checked /> SKIPPED</label>',
            "          </div>",
            "        </div>",
            '        <div class="actions">',
            '          <button id="help-btn" class="btn" type="button">Help</button>',
            '          <button id="expand-all" class="btn" type="button">Expand all</button>',
            '          <button id="collapse-all" class="btn" type="button">Collapse all</button>',
            "        </div>",
            "      </div>",
            '      <div class="summary">',
            f'        <div class="card"><div class="k">Total checks</div><div class="v">{len(all_results)}</div></div>',
            f'        <div class="card ok"><div class="k">OK</div><div class="v">{count_ok}</div></div>',
            f'        <div class="card warn"><div class="k">WARN</div><div class="v">{count_warn}</div></div>',
            f'        <div class="card bad"><div class="k">BAD</div><div class="v">{count_bad}</div></div>',
            f'        <div class="card"><div class="k">Skipped</div><div class="v">{count_skipped}</div></div>',
            f'        <div class="card"><div class="k">Runtime (sum)</div><div class="v">{total_runtime:.1f}s</div></div>',
            "      </div>",
            "    </header>",
            '    <div class="toc"><h2>Sections</h2><div class="tocgrid">' + toc_items + "</div></div>",
            sections_html,
            '    <section><h2>Actions (Not Run)</h2><div class="block"><pre>'
            + html.escape(actions_not_run)
            + "</pre></div></section>",
            "    <footer>Tip: re-run with <code>--include-heavy</code>, <code>--include-network</code>, <code>--include-profiler</code>, and/or <code>--include-logs</code> for deeper checks.</footer>",
            '    <div id="help-modal" class="modal" role="dialog" aria-modal="true" aria-label="Report help">',
            '      <div class="dialog">',
            '        <div class="dialoghead">',
            "          <h3>How to run this report</h3>",
            '          <button id="help-close" class="btn" type="button">Close <span class="kbd">(Esc)</span></button>',
            "        </div>",
            '        <div class="dialogbody">',
            f"          <pre>{html.escape(report_help_text())}</pre>",
            "        </div>",
            "      </div>",
            "    </div>",
            f"    <script>{js}</script>",
            "  </div>",
            "</body>",
            "</html>",
        ]
    )

    css_path.write_text(CSS_TEXT, encoding="utf-8")
    html_path.write_text(page, encoding="utf-8")

    log(f"Report written: {html_path}")
    log(f"Stylesheet: {css_path}")
    return html_path


# ------------------------
# Maintenance tasks
# ------------------------

def validate_home_path(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    home = Path.home().resolve()
    if not str(resolved).startswith(str(home)):
        raise ValueError(f"{label} must be within {home}")
    return resolved


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def human_size_kb(kb: int) -> str:
    gb = kb / 1024 / 1024
    return f"{gb:.2f} GB"


def du_kb(path: Path) -> Optional[int]:
    try:
        proc = subprocess.run(["/usr/bin/du", "-sk", str(path)], text=True, capture_output=True, check=False)
        if proc.returncode != 0:
            return None
        return int(proc.stdout.split()[0])
    except Exception:
        return None


def task_cleanup_archives(archive_dir: Path, mode: str) -> None:
    archive_dir = validate_home_path(archive_dir, "archive-dir")
    if not archive_dir.exists():
        log(f"cleanup-archives: directory not found: {archive_dir}")
        return

    today = dt.date.today().strftime("%Y-%m-%d")
    pattern = re.compile(r".*_delete_([0-9]{4}-[0-9]{2}-[0-9]{2})\.zip$")

    candidates: List[Path] = []
    for p in archive_dir.glob("*_delete_*.zip"):
        m = pattern.match(p.name)
        if not m:
            continue
        delete_date = m.group(1)
        if delete_date <= today:
            candidates.append(p)

    if not candidates:
        log("cleanup-archives: no archives eligible for deletion")
        return

    log(f"cleanup-archives: {len(candidates)} archive(s) eligible for deletion")
    for p in candidates:
        size = du_kb(p)
        size_str = human_size_kb(size) if size else "unknown"
        if mode == MODE_APPLY:
            try:
                p.unlink()
                log(f"deleted: {p.name} ({size_str})")
            except Exception as e:
                log(f"failed to delete {p.name}: {e}")
        else:
            log(f"would delete: {p.name} ({size_str})")


def task_archive_orphans(app_support_dir: Path, archive_dir: Path, folders: List[str], days: int, mode: str) -> None:
    app_support_dir = app_support_dir.expanduser().resolve()
    archive_dir = validate_home_path(archive_dir, "archive-dir")
    ensure_dir(archive_dir)

    delete_date = (dt.date.today() + dt.timedelta(days=days)).strftime("%Y-%m-%d")
    log(f"archive-orphans: delete date set to {delete_date}")

    for folder in folders:
        folder_path = app_support_dir / folder
        if not folder_path.is_dir():
            log(f"skip (not found): {folder}")
            continue

        archive_name = f"{folder.replace(' ', '_')}_delete_{delete_date}.zip"
        archive_path = archive_dir / archive_name

        if mode != MODE_APPLY:
            log(f"would archive: {folder} -> {archive_path}")
            continue

        try:
            log(f"archiving: {folder}")
            proc = subprocess.run([
                "/usr/bin/zip",
                "-r",
                str(archive_path),
                folder,
            ], cwd=str(app_support_dir), text=True, capture_output=True, check=False)
            if proc.returncode != 0:
                log(f"zip failed for {folder}: {proc.stderr.strip()}")
                continue
            shutil.rmtree(folder_path)
            log(f"archived and removed: {folder}")
        except Exception as e:
            log(f"archive failed for {folder}: {e}")


def task_find_orphans(app_support_dir: Path, applications_dir: Path, limit: int, skip_re: re.Pattern[str]) -> None:
    app_support_dir = app_support_dir.expanduser().resolve()
    applications_dir = applications_dir.expanduser().resolve()

    if not app_support_dir.is_dir():
        log(f"find-orphans: Application Support not found: {app_support_dir}")
        return

    installed_apps: List[str] = []
    try:
        for entry in applications_dir.iterdir():
            if entry.name.endswith(".app"):
                installed_apps.append(entry.name[:-4].lower())
    except Exception as e:
        log(f"find-orphans: failed to list /Applications: {e}")
        return

    support_dirs = sorted([p.name for p in app_support_dir.iterdir() if p.is_dir()])

    orphans: List[str] = []
    for support_dir in support_dirs:
        if skip_re.match(support_dir):
            continue
        support_lower = support_dir.lower()
        found = False
        for app in installed_apps:
            if support_lower in app or app in support_lower:
                found = True
                break
        if not found:
            orphans.append(support_dir)

    log(f"find-orphans: found {len(orphans)} potential orphaned folders")
    for name in orphans[:limit]:
        full = app_support_dir / name
        size = du_kb(full)
        size_str = human_size_kb(size) if size else "unknown"
        try:
            mtime = dt.datetime.fromtimestamp(full.stat().st_mtime).strftime("%Y-%m-%d")
        except Exception:
            mtime = "unknown"
        log(f"  {name} ({size_str}, last modified: {mtime})")


def validate_brew_bin(brew_bin: str) -> str:
    if not brew_bin.startswith("/"):
        raise ValueError("brew bin must be an absolute path")
    if not os.path.exists(brew_bin) or not os.access(brew_bin, os.X_OK):
        raise ValueError(f"brew bin not executable: {brew_bin}")
    return brew_bin


def run_brew(brew_bin: str, args: List[str], timeout_s: Optional[int] = None) -> subprocess.CompletedProcess:
    cmd = [brew_bin] + args
    log("→ " + " ".join(shlex.quote(a) for a in cmd))
    return subprocess.run(cmd, text=True, capture_output=True, check=False, timeout=timeout_s)


def task_brew_maintenance(
    *,
    mode: str,
    brew_bin: str,
    list_file: Path,
    cask_file: Path,
    do_update: bool,
    do_upgrade: bool,
    do_upgrade_cask: bool,
    do_autoremove: bool,
    do_cleanup: bool,
    do_doctor: bool,
    do_missing: bool,
    do_list: bool,
    do_cask_list: bool,
    do_untap: bool,
    do_fix_casks: bool,
    fix_casks: List[str],
) -> None:
    brew_bin = validate_brew_bin(brew_bin)
    list_file = validate_home_path(list_file, "brew list file")
    cask_file = validate_home_path(cask_file, "brew cask file")

    def maybe_run(desc: str, args: List[str], *, allow_in_report: bool = False) -> None:
        if mode == MODE_REPORT and not allow_in_report:
            log(f"brew: report mode skip {desc}")
            return
        if mode == MODE_DRY_RUN:
            log(f"brew: would run {desc}: {' '.join(args)}")
            return
        proc = run_brew(brew_bin, args)
        if proc.returncode != 0:
            log(f"brew: {desc} failed: {proc.stderr.strip()}")

    if mode in (MODE_REPORT, MODE_DRY_RUN):
        if not any([
            do_update,
            do_upgrade,
            do_upgrade_cask,
            do_autoremove,
            do_cleanup,
            do_doctor,
            do_missing,
            do_list,
            do_cask_list,
            do_untap,
            do_fix_casks,
        ]):
            do_doctor = True
            do_list = True
            do_cask_list = True

    if do_update:
        maybe_run("update", ["update"])
    if do_upgrade:
        maybe_run("upgrade", ["upgrade"])
    if do_upgrade_cask:
        maybe_run("upgrade cask", ["upgrade", "--cask", "--greedy"])
    if do_autoremove:
        maybe_run("autoremove", ["autoremove"])
    if do_cleanup:
        maybe_run("cleanup", ["cleanup", "--prune=7", "--quiet"])
    if do_doctor:
        maybe_run("doctor", ["doctor"], allow_in_report=True)
    if do_missing:
        maybe_run("missing", ["missing"], allow_in_report=True)
    if do_untap:
        maybe_run("untap", ["untap", "--force", "Homebrew/homebrew-bundle", "Homebrew/homebrew-services"])

    if do_list:
        if mode == MODE_DRY_RUN:
            log(f"brew: would write list to {list_file}")
        elif mode == MODE_REPORT:
            proc = run_brew(brew_bin, ["list"])
            if proc.returncode == 0:
                list_file.write_text(proc.stdout)
                log(f"brew: wrote list to {list_file}")
            else:
                log(f"brew: list failed: {proc.stderr.strip()}")
        else:
            proc = run_brew(brew_bin, ["list"])
            if proc.returncode == 0:
                list_file.write_text(proc.stdout)
                log(f"brew: wrote list to {list_file}")
            else:
                log(f"brew: list failed: {proc.stderr.strip()}")

    if do_cask_list:
        if mode == MODE_DRY_RUN:
            log(f"brew: would write cask list to {cask_file}")
        else:
            proc = run_brew(brew_bin, ["list", "--cask"])
            if proc.returncode == 0:
                cask_file.write_text(proc.stdout)
                log(f"brew: wrote cask list to {cask_file}")
            else:
                log(f"brew: cask list failed: {proc.stderr.strip()}")

    if do_fix_casks:
        missing_casks: List[str] = []
        proc = run_brew(brew_bin, ["list", "--cask"])
        if proc.returncode != 0:
            log("brew: could not list casks for fix")
            return
        installed = [line.strip().lower() for line in proc.stdout.splitlines() if line.strip()]
        for app in fix_casks:
            app_lower = app.lower()
            if app_lower in installed and not (Path("/Applications") / f"{app}.app").exists():
                if app == "JupyterLab":
                    missing_casks.append("jupyterlab-app")
                elif app == "LosslessCut":
                    missing_casks.append("losslesscut")
                elif app == "RsyncUI":
                    missing_casks.append("rsyncui")
                else:
                    missing_casks.append(app_lower)

        if not missing_casks:
            log("brew: no missing cask apps detected")
            return

        if mode != MODE_APPLY:
            log(f"brew: would reinstall missing casks: {', '.join(missing_casks)}")
            return

        log(f"brew: reinstalling missing casks: {', '.join(missing_casks)}")
        run_brew(brew_bin, ["uninstall", "--cask"] + missing_casks)
        run_brew(brew_bin, ["install", "--cask"] + missing_casks)


def chrome_running() -> bool:
    proc = subprocess.run(["/usr/bin/pgrep", "-f", "Google Chrome Beta"], capture_output=True)
    return proc.returncode == 0


def close_chrome() -> bool:
    subprocess.run(["/usr/bin/osascript", "-e", 'quit app "Google Chrome Beta"'], capture_output=True)
    time.sleep(3)
    if not chrome_running():
        return True
    subprocess.run(["/usr/bin/pkill", "-TERM", "-f", "Google Chrome Beta"], capture_output=True)
    time.sleep(5)
    if not chrome_running():
        return True
    subprocess.run(["/usr/bin/pkill", "-KILL", "-f", "Google Chrome Beta"], capture_output=True)
    time.sleep(2)
    return not chrome_running()


def task_chrome_cleanup(chrome_dir: Path, mode: str, kill_chrome: bool) -> None:
    chrome_dir = validate_home_path(chrome_dir, "chrome-dir")
    if not chrome_dir.exists():
        log(f"chrome-cleanup: directory not found: {chrome_dir}")
        return

    if chrome_running():
        if not kill_chrome:
            log("chrome-cleanup: Chrome Beta is running. Use --kill-chrome to close it.")
            return
        if mode != MODE_APPLY:
            log("chrome-cleanup: would close Chrome Beta")
            return
        if not close_chrome():
            log("chrome-cleanup: failed to close Chrome Beta")
            return

    profiles = []
    for entry in chrome_dir.iterdir():
        if entry.is_dir() and (entry.name == "Default" or entry.name.startswith("Profile ")):
            profiles.append(entry.name)

    if not profiles:
        log("chrome-cleanup: no profiles found")
        return

    log(f"chrome-cleanup: found {len(profiles)} profile(s)")
    for profile in profiles:
        profile_path = chrome_dir / profile
        size = du_kb(profile_path)
        size_str = human_size_kb(size) if size else "unknown"
        log(f"  {profile}: {size_str}")

    for profile in profiles:
        profile_path = chrome_dir / profile
        for name in CHROME_CLEAN_DIRS:
            dir_path = profile_path / name
            if not dir_path.is_dir():
                continue
            if mode == MODE_APPLY:
                for root, dirs, files in os.walk(dir_path):
                    for f in files:
                        try:
                            (Path(root) / f).unlink()
                        except Exception:
                            pass
                    for d in dirs:
                        try:
                            shutil.rmtree(Path(root) / d, ignore_errors=True)
                        except Exception:
                            pass
                log(f"cleaned: {profile}/{name}")
            else:
                log(f"would clean: {profile}/{name}")


def task_copy_speed_test(src: Path, dst: Path, mode: str) -> None:
    src = src.expanduser().resolve()
    dst = dst.expanduser().resolve()
    if not src.exists():
        log(f"copy-speed-test: source not found: {src}")
        return
    if not dst.parent.exists():
        log(f"copy-speed-test: destination parent missing: {dst.parent}")
        return

    size_kb = du_kb(src)
    if size_kb:
        log(f"copy-speed-test: source size {human_size_kb(size_kb)}")

    if mode != MODE_APPLY:
        log(f"copy-speed-test: would copy {src} -> {dst}")
        return

    log(f"copy-speed-test: starting copy {src} -> {dst}")
    start = time.time()
    proc = subprocess.run([
        "/usr/bin/rsync",
        "-ah",
        "--progress",
        "--partial",
        "--inplace",
        "--compress-level=1",
        str(src),
        str(dst),
    ], text=True)
    end = time.time()
    duration = max(1, int(end - start))
    if proc.returncode != 0:
        log(f"copy-speed-test: rsync failed with {proc.returncode}")
        return
    if size_kb:
        speed = (size_kb / 1024) / duration
        log(f"copy-speed-test: avg speed {speed:.2f} MB/s")
    log(f"copy-speed-test: completed in {duration}s")


def report_help_text() -> str:
    return """\
Examples:
  - Report only (HTML):
      python3 mac_maintenance.py --mode report --task report-html --report-out-dir .

  - Dry-run on maintenance tasks:
      python3 mac_maintenance.py --mode dry-run --task brew-maintenance --task cleanup-archives

  - Apply with explicit actions:
      python3 mac_maintenance.py --mode apply --task brew-maintenance --brew-update --brew-upgrade

Report UI tips:
  - Filter checks by typing in the search box.
  - Toggle OK/WARN/BAD/SKIPPED to focus on issues.
  - Use “Expand all” to quickly view everything.
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Unified macOS maintenance tool.")
    parser.add_argument("--mode", choices=[MODE_REPORT, MODE_DRY_RUN, MODE_APPLY], default=MODE_REPORT)
    parser.add_argument(
        "--task",
        action="append",
        choices=[
            TASK_REPORT,
            TASK_BREW,
            TASK_FIND_ORPHANS,
            TASK_ARCHIVE_ORPHANS,
            TASK_CLEANUP_ARCHIVES,
            TASK_CHROME,
            TASK_COPY,
        ],
        help="Task to run (repeatable).",
    )

    parser.add_argument("--report-out-dir", default=str(Path.cwd()))
    parser.add_argument("--include-network", action="store_true")
    parser.add_argument("--include-heavy", action="store_true")
    parser.add_argument("--include-profiler", action="store_true")
    parser.add_argument("--include-logs", action="store_true")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--max-chars", type=int, default=20000)
    parser.add_argument("--max-lines", type=int, default=500)

    parser.add_argument("--brew-bin", default=os.environ.get("BREW", "/opt/homebrew/bin/brew"))
    parser.add_argument("--brew-list-file", default=str(Path.home() / ".brew-list.txt"))
    parser.add_argument("--brew-cask-file", default=str(Path.home() / ".brew-cask.txt"))
    parser.add_argument("--brew-update", action="store_true")
    parser.add_argument("--brew-upgrade", action="store_true")
    parser.add_argument("--brew-upgrade-cask", action="store_true")
    parser.add_argument("--brew-autoremove", action="store_true")
    parser.add_argument("--brew-cleanup", action="store_true")
    parser.add_argument("--brew-doctor", action="store_true")
    parser.add_argument("--brew-missing", action="store_true")
    parser.add_argument("--brew-list", action="store_true")
    parser.add_argument("--brew-cask-list", action="store_true")
    parser.add_argument("--brew-untap", action="store_true")
    parser.add_argument("--brew-fix-missing-casks", action="store_true")
    parser.add_argument("--brew-fix-cask", action="append", default=[])

    parser.add_argument("--app-support-dir", default=str(Path.home() / "Library/Application Support"))
    parser.add_argument("--applications-dir", default="/Applications")
    parser.add_argument("--orphans-limit", type=int, default=DEFAULT_ORPHANS_LIMIT)

    parser.add_argument("--archive-dir", default=str(Path.home() / "Desktop/Orphaned_App_Support_Archives"))
    parser.add_argument("--archive-days", type=int, default=DEFAULT_ARCHIVE_DAYS)
    parser.add_argument("--archive-folder", action="append", default=[])

    parser.add_argument("--chrome-dir", default=str(Path.home() / "Library/Application Support/Google/Chrome Beta"))
    parser.add_argument("--kill-chrome", action="store_true")

    parser.add_argument("--copy-src", default=str(Path("/Users/jpaul/Virtual Machines.localized")))
    parser.add_argument("--copy-dst", default=str(Path("/Volumes/VMware")))

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    mode = args.mode
    tasks = args.task or []

    if not tasks:
        if mode == MODE_REPORT:
            tasks = [TASK_REPORT]
        else:
            log("No tasks selected. Use --task to choose what to run.")
            return 2

    if TASK_REPORT in tasks:
        generate_report(
            out_dir=Path(args.report_out_dir),
            include_network=args.include_network,
            include_heavy=args.include_heavy,
            include_profiler=args.include_profiler,
            include_logs=args.include_logs,
            timeout=args.timeout,
            max_chars=args.max_chars,
            max_lines=args.max_lines,
        )

    if TASK_BREW in tasks:
        fix_list = args.brew_fix_cask or DEFAULT_MISSING_CASK_APPS
        task_brew_maintenance(
            mode=mode,
            brew_bin=args.brew_bin,
            list_file=Path(args.brew_list_file),
            cask_file=Path(args.brew_cask_file),
            do_update=args.brew_update,
            do_upgrade=args.brew_upgrade,
            do_upgrade_cask=args.brew_upgrade_cask,
            do_autoremove=args.brew_autoremove,
            do_cleanup=args.brew_cleanup,
            do_doctor=args.brew_doctor,
            do_missing=args.brew_missing,
            do_list=args.brew_list,
            do_cask_list=args.brew_cask_list,
            do_untap=args.brew_untap,
            do_fix_casks=args.brew_fix_missing_casks,
            fix_casks=fix_list,
        )

    if TASK_FIND_ORPHANS in tasks:
        task_find_orphans(
            app_support_dir=Path(args.app_support_dir),
            applications_dir=Path(args.applications_dir),
            limit=args.orphans_limit,
            skip_re=DEFAULT_ORPHANS_SKIP_RE,
        )

    if TASK_ARCHIVE_ORPHANS in tasks:
        folders = args.archive_folder or DEFAULT_ARCHIVE_FOLDERS
        task_archive_orphans(
            app_support_dir=Path(args.app_support_dir),
            archive_dir=Path(args.archive_dir),
            folders=folders,
            days=args.archive_days,
            mode=mode,
        )

    if TASK_CLEANUP_ARCHIVES in tasks:
        task_cleanup_archives(Path(args.archive_dir), mode)

    if TASK_CHROME in tasks:
        task_chrome_cleanup(Path(args.chrome_dir), mode, args.kill_chrome)

    if TASK_COPY in tasks:
        task_copy_speed_test(Path(args.copy_src), Path(args.copy_dst), mode)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
