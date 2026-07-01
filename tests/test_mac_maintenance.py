import importlib.util
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest


def load_module():
    path = Path(__file__).parent.parent / "mac-maintenance.py"
    spec = importlib.util.spec_from_file_location("mac_maintenance", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # Ensure module is registered for dataclasses + future annotations
    import sys
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def home_tmp_path():
    # validate_home_path() requires paths under Path.home(), so pytest's own
    # tmp_path (under /private/var/folders/...) doesn't satisfy it.
    path = Path(tempfile.mkdtemp(dir=Path.home(), prefix=".mac_maintenance_test_"))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def test_validate_home_path_ok():
    m = load_module()
    home = Path.home()
    p = home / "Documents"
    assert m.validate_home_path(p, "test") == p.expanduser().resolve()


def test_validate_home_path_rejects_outside():
    m = load_module()
    with pytest.raises(ValueError):
        m.validate_home_path(Path("/etc"), "test")


def test_validate_home_path_rejects_sibling_prefix():
    m = load_module()
    home = Path.home()
    sibling = home.parent / (home.name + "evil")
    with pytest.raises(ValueError):
        m.validate_home_path(sibling, "test")


def test_parse_ioreg_model_matches_real_output():
    m = load_module()
    sample = '"model" = <"Mac17,6">\n"model-number" = <5a314e3230303031410000>'
    model, model_number = m.parse_ioreg_model(sample)
    assert model == "Mac17,6"
    assert model_number == "Z1N20001A"


def test_parse_ioreg_model_no_match_returns_none():
    m = load_module()
    model, model_number = m.parse_ioreg_model("")
    assert model is None
    assert model_number is None


def test_default_orphans_skip_re_matches_real_folder_names():
    m = load_module()
    assert m.DEFAULT_ORPHANS_SKIP_RE.match("com.apple.Safari")
    assert m.DEFAULT_ORPHANS_SKIP_RE.match("default.store")
    assert not m.DEFAULT_ORPHANS_SKIP_RE.match("SomeRealApp")


def test_human_size_kb_uses_appropriate_unit():
    m = load_module()
    assert m.human_size_kb(1) == "1 KB"
    assert m.human_size_kb(2048) == "2.00 MB"
    assert m.human_size_kb(2 * 1024 * 1024) == "2.00 GB"


def test_parse_login_item_labels_matches_real_output():
    m = load_module()
    sample = '"io.mountainduck.loginitem" => enabled\ncom.apple.xpc.loginitemregisterd'
    assert m.parse_login_item_labels(sample) == ["io.mountainduck.loginitem"]


def test_parse_login_item_labels_excludes_apple():
    m = load_module()
    sample = '"com.apple.something.loginitem" => enabled'
    assert m.parse_login_item_labels(sample) == []


def test_copy_speed_test_dry_run_no_rsync(tmp_path, monkeypatch, capsys):
    m = load_module()
    src = tmp_path / "src"
    src.mkdir()
    dst = tmp_path / "dest"

    monkeypatch.setattr(m, "du_kb", lambda _p: 1024)

    def fail_run(*_args, **_kwargs):
        raise AssertionError("subprocess.run should not be called in dry-run")

    monkeypatch.setattr(m.subprocess, "run", fail_run)

    m.task_copy_speed_test(src, dst, m.MODE_DRY_RUN)
    out = capsys.readouterr().out
    assert "would copy" in out


def test_cleanup_archives_dry_run_keeps_files(home_tmp_path, capsys):
    m = load_module()
    base = home_tmp_path / "cleanup_archives"
    base.mkdir(parents=True, exist_ok=True)
    archive_dir = base / "archives"
    archive_dir.mkdir(parents=True, exist_ok=True)
    # Past date should be eligible
    p = archive_dir / "test_delete_2000-01-01.zip"
    p.write_text("x")

    m.task_cleanup_archives(archive_dir, m.MODE_DRY_RUN)
    assert p.exists()
    out = capsys.readouterr().out
    assert "would delete" in out


def test_archive_orphans_dry_run_no_delete(home_tmp_path, capsys):
    m = load_module()
    base = home_tmp_path / "archive_orphans"
    base.mkdir(parents=True, exist_ok=True)
    app_support = base / "Application Support"
    app_support.mkdir(parents=True, exist_ok=True)
    folder = app_support / "SomeApp"
    folder.mkdir(exist_ok=True)
    archive_dir = base / "archives"

    m.task_archive_orphans(app_support, archive_dir, ["SomeApp"], 10, m.MODE_DRY_RUN)
    assert folder.exists()
    assert not archive_dir.exists()
    out = capsys.readouterr().out
    assert "would archive" in out


def test_brew_maintenance_dry_run_no_brew(monkeypatch, tmp_path, home_tmp_path, capsys):
    m = load_module()
    # Fake brew binary
    brew = tmp_path / "brew"
    brew.write_text("#!/bin/sh\nexit 0\n")
    brew.chmod(0o755)

    def fail_run(*_args, **_kwargs):
        raise AssertionError("brew should not run in dry-run")

    monkeypatch.setattr(m, "run_brew", fail_run)

    base = home_tmp_path / "brew_lists"
    base.mkdir(parents=True, exist_ok=True)

    m.task_brew_maintenance(
        mode=m.MODE_DRY_RUN,
        brew_bin=str(brew),
        list_file=base / "list.txt",
        cask_file=base / "cask.txt",
        do_update=True,
        do_upgrade=True,
        do_upgrade_cask=False,
        do_autoremove=False,
        do_cleanup=False,
        do_doctor=True,
        do_missing=False,
        do_list=True,
        do_cask_list=True,
        do_untap=False,
        do_fix_casks=False,
        fix_casks=[],
    )
    out = capsys.readouterr().out
    assert "would run" in out
    assert "would write list" in out


def test_brew_maintenance_report_mode_no_write(monkeypatch, tmp_path, home_tmp_path, capsys):
    m = load_module()
    brew = tmp_path / "brew"
    brew.write_text("#!/bin/sh\nexit 0\n")
    brew.chmod(0o755)

    def fail_run(*_args, **_kwargs):
        raise AssertionError("brew should not run for list/cask-list in report mode")

    monkeypatch.setattr(m, "run_brew", fail_run)

    base = home_tmp_path / "brew_report_lists"
    base.mkdir(parents=True, exist_ok=True)
    list_file = base / "list.txt"
    cask_file = base / "cask.txt"

    m.task_brew_maintenance(
        mode=m.MODE_REPORT,
        brew_bin=str(brew),
        list_file=list_file,
        cask_file=cask_file,
        do_update=False,
        do_upgrade=False,
        do_upgrade_cask=False,
        do_autoremove=False,
        do_cleanup=False,
        do_doctor=False,
        do_missing=False,
        do_list=True,
        do_cask_list=True,
        do_untap=False,
        do_fix_casks=False,
        fix_casks=[],
    )
    assert not list_file.exists()
    assert not cask_file.exists()


def test_fix_casks_skips_install_when_uninstall_fails(monkeypatch, tmp_path, home_tmp_path, capsys):
    m = load_module()
    brew = tmp_path / "brew"
    brew.write_text("#!/bin/sh\nexit 0\n")
    brew.chmod(0o755)

    calls = []

    def fake_run_brew(_brew_bin, args):
        calls.append(args)
        if args[:2] == ["list", "--cask"]:
            return subprocess.CompletedProcess(args, 0, stdout="jupyterlab\n", stderr="")
        if args[:2] == ["uninstall", "--cask"]:
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="uninstall failed")
        if args[:2] == ["install", "--cask"]:
            raise AssertionError("install should not run when uninstall fails")
        raise AssertionError(f"unexpected brew args: {args}")

    monkeypatch.setattr(m, "run_brew", fake_run_brew)
    monkeypatch.setattr(m.Path, "exists", lambda _self: False)

    base = home_tmp_path / "fix_casks_lists"
    base.mkdir(parents=True, exist_ok=True)

    m.task_brew_maintenance(
        mode=m.MODE_APPLY,
        brew_bin=str(brew),
        list_file=base / "list.txt",
        cask_file=base / "cask.txt",
        do_update=False,
        do_upgrade=False,
        do_upgrade_cask=False,
        do_autoremove=False,
        do_cleanup=False,
        do_doctor=False,
        do_missing=False,
        do_list=False,
        do_cask_list=False,
        do_untap=False,
        do_fix_casks=True,
        fix_casks=["JupyterLab"],
    )
    assert ["uninstall", "--cask", "jupyterlab-app"] in calls
    assert not any(c[:2] == ["install", "--cask"] for c in calls)


def test_render_results_section_closing_order():
    m = load_module()
    r = m.CommandResult(
        title="t",
        command="cmd",
        duration_s=0.1,
        returncode=0,
        stdout="ok",
        stderr="",
    )
    section = m.ReportSection("S", "s", [r])
    html = m.render_results_section(section)
    # ensure block closes details before the block div
    assert "</details>\n</div>" in html


def test_generate_report_writes_files(tmp_path, monkeypatch):
    m = load_module()

    def dummy_cmd(*_args, **_kwargs):
        return m.CommandResult(
            title="t",
            command="cmd",
            duration_s=0.0,
            returncode=0,
            stdout="ok",
            stderr="",
        )

    monkeypatch.setattr(m, "run_command", dummy_cmd)
    monkeypatch.setattr(m, "hardware_quick_summary_result", lambda **_k: dummy_cmd())
    monkeypatch.setattr(m, "login_items_quick_result", lambda **_k: dummy_cmd())

    html_path = m.generate_report(
        out_dir=tmp_path,
        include_network=False,
        include_heavy=False,
        include_profiler=False,
        include_logs=False,
        timeout=1.0,
        max_chars=100,
        max_lines=10,
    )

    assert html_path.exists()
    css_path = html_path.with_suffix(".css")
    assert css_path.exists()


def _set_mtime(path, age_seconds):
    import os
    import time
    old_time = time.time() - age_seconds
    os.utime(path, (old_time, old_time))


def _touch_with_mtime(path, age_seconds, content="x"):
    path.write_text(content)
    _set_mtime(path, age_seconds)


def test_clean_dir_contents_dry_run_keeps_files(home_tmp_path, capsys):
    m = load_module()
    target = home_tmp_path / "caches"
    target.mkdir()
    old_file = target / "stale.cache"
    _touch_with_mtime(old_file, age_seconds=3600)

    m._clean_dir_contents(target, m.MODE_DRY_RUN, "clean-caches", min_age_s=300.0)
    assert old_file.exists()
    out = capsys.readouterr().out
    assert "would delete" in out
    assert "stale.cache" in out


def test_clean_dir_contents_skips_recently_modified_entries(home_tmp_path, capsys):
    m = load_module()
    target = home_tmp_path / "caches"
    target.mkdir()
    recent_file = target / "fresh.cache"
    _touch_with_mtime(recent_file, age_seconds=1)

    m._clean_dir_contents(target, m.MODE_APPLY, "clean-caches", min_age_s=300.0)
    assert recent_file.exists()
    out = capsys.readouterr().out
    assert "skipped 1 recently-modified entry" in out


def test_clean_dir_contents_apply_deletes_old_entries(home_tmp_path, capsys):
    m = load_module()
    target = home_tmp_path / "caches"
    target.mkdir()
    old_file = target / "stale.cache"
    _touch_with_mtime(old_file, age_seconds=3600)

    m._clean_dir_contents(target, m.MODE_APPLY, "clean-caches", min_age_s=300.0)
    assert not old_file.exists()
    out = capsys.readouterr().out
    assert "deleted stale.cache" in out


def test_task_clean_caches_uses_clean_caches_label(home_tmp_path, capsys):
    m = load_module()
    target = home_tmp_path / "Caches"
    target.mkdir()
    m.task_clean_caches(target, m.MODE_DRY_RUN, min_age_s=0.0)
    out = capsys.readouterr().out
    assert "clean-caches: nothing eligible" in out


def test_task_empty_trash_uses_empty_trash_label(home_tmp_path, capsys):
    m = load_module()
    target = home_tmp_path / "Trash"
    target.mkdir()
    m.task_empty_trash(target, m.MODE_DRY_RUN)
    out = capsys.readouterr().out
    assert "empty-trash: nothing eligible" in out


def test_task_clean_logs_uses_clean_logs_label(home_tmp_path, capsys):
    m = load_module()
    target = home_tmp_path / "Logs"
    target.mkdir()
    m.task_clean_logs(target, m.MODE_DRY_RUN, min_age_s=0.0)
    out = capsys.readouterr().out
    assert "clean-logs: nothing eligible" in out


def test_clean_ios_backups_keeps_latest_n_dry_run(home_tmp_path, capsys):
    m = load_module()
    backups_dir = home_tmp_path / "Backup"
    backups_dir.mkdir()
    newest = backups_dir / "newest-uuid"
    newest.mkdir()
    _set_mtime(newest, age_seconds=10)
    oldest = backups_dir / "oldest-uuid"
    oldest.mkdir()
    _set_mtime(oldest, age_seconds=999999)

    m.task_clean_ios_backups(backups_dir, m.MODE_DRY_RUN, keep_latest=1)
    out = capsys.readouterr().out
    assert "keeping newest-uuid" in out
    assert "would delete oldest-uuid" in out
    assert newest.exists()
    assert oldest.exists()


def test_clean_ios_backups_rejects_keep_zero(home_tmp_path, capsys):
    m = load_module()
    backups_dir = home_tmp_path / "Backup"
    backups_dir.mkdir()
    (backups_dir / "some-uuid").mkdir()

    m.task_clean_ios_backups(backups_dir, m.MODE_APPLY, keep_latest=0)
    out = capsys.readouterr().out
    assert "refusing to delete all backups" in out
    assert (backups_dir / "some-uuid").exists()


def test_installed_bundle_ids_reads_info_plist(tmp_path):
    m = load_module()
    apps_dir = tmp_path / "Applications"
    apps_dir.mkdir()
    contents_dir = apps_dir / "Slack.app" / "Contents"
    contents_dir.mkdir(parents=True)
    with (contents_dir / "Info.plist").open("wb") as f:
        m.plistlib.dump({"CFBundleIdentifier": "com.tinyspeck.slackmacgap"}, f)

    result = m.installed_bundle_ids(apps_dir)
    assert result == {"com.tinyspeck.slackmacgap": "Slack"}


def test_find_bundle_orphans_matches_exact_bundle_id(monkeypatch, tmp_path, capsys):
    m = load_module()
    apps_dir = tmp_path / "Applications"
    apps_dir.mkdir()
    contents_dir = apps_dir / "Slack.app" / "Contents"
    contents_dir.mkdir(parents=True)
    with (contents_dir / "Info.plist").open("wb") as f:
        m.plistlib.dump({"CFBundleIdentifier": "com.tinyspeck.slackmacgap"}, f)

    fake_home = tmp_path / "home"
    containers = fake_home / "Library" / "Containers"
    containers.mkdir(parents=True)
    (containers / "com.tinyspeck.slackmacgap").mkdir()
    (containers / "com.someoldapp.leftover").mkdir()
    (containers / "com.apple.somesystemthing").mkdir()
    (containers / "00F2F88D-E153-49FF-9C2D-87944A99BEE2").mkdir()
    (containers / ".GlobalPreferences").mkdir()

    monkeypatch.setattr(m.Path, "home", classmethod(lambda cls: fake_home))

    m.task_find_bundle_orphans(apps_dir, limit=10)
    out = capsys.readouterr().out
    assert "containers/com.someoldapp.leftover" in out
    assert "containers/com.tinyspeck.slackmacgap" not in out
    assert "containers/com.apple.somesystemthing" not in out
    assert "00F2F88D-E153-49FF-9C2D-87944A99BEE2" not in out
    assert "containers/.GlobalPreferences" not in out


def test_process_running_reads_pgrep_returncode(monkeypatch):
    m = load_module()
    calls = []

    def fake_run(argv, **_kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(m.subprocess, "run", fake_run)
    assert m.process_running("Some App") is True
    # -x (exact name match), NOT -f (command-line substring) — see process_running docstring.
    assert calls == [["/usr/bin/pgrep", "-x", "Some App"]]


def test_process_running_false_when_pgrep_nonzero(monkeypatch):
    m = load_module()
    monkeypatch.setattr(
        m.subprocess, "run",
        lambda argv, **_k: subprocess.CompletedProcess(argv, 1),
    )
    assert m.process_running("Nope") is False


def test_close_app_uses_exact_match_pkill(monkeypatch):
    m = load_module()
    calls = []

    def fake_run(argv, **_k):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(m.subprocess, "run", fake_run)
    monkeypatch.setattr(m.time, "sleep", lambda _s: None)
    # Report still-running after every attempt so both pkill fallbacks fire.
    monkeypatch.setattr(m, "process_running", lambda name: True)

    result = m.close_app("Safari")
    assert result is False  # still running after KILL
    # osascript quit first, then TERM and KILL both with -x (exact), never -f.
    assert calls[0][:2] == ["/usr/bin/osascript", "-e"]
    assert ["/usr/bin/pkill", "-TERM", "-x", "Safari"] in calls
    assert ["/usr/bin/pkill", "-KILL", "-x", "Safari"] in calls
    assert not any("-f" in c for c in calls)


def test_chrome_cleanup_uses_custom_process_name(monkeypatch, home_tmp_path, capsys):
    m = load_module()
    seen = []
    monkeypatch.setattr(m, "process_running", lambda name: seen.append(name) or True)

    chrome_dir = home_tmp_path / "Chrome"
    chrome_dir.mkdir()

    # Running + no kill flag -> should bail with a message naming the custom process.
    m.task_chrome_cleanup(chrome_dir, m.MODE_DRY_RUN, kill_chrome=False,
                          process_name="Google Chrome")
    out = capsys.readouterr().out
    assert seen == ["Google Chrome"]
    assert "Google Chrome is running" in out
    assert "Chrome Beta" not in out


def test_safari_cleanup_visits_all_targets_dry_run(monkeypatch, home_tmp_path, capsys):
    m = load_module()
    monkeypatch.setattr(m, "process_running", lambda name: False)

    cache = home_tmp_path / "cache"
    fav = home_tmp_path / "fav"
    web = home_tmp_path / "web"
    for d in (cache, fav, web):
        d.mkdir()

    m.task_safari_cleanup(m.MODE_DRY_RUN, False, cache, fav, web)
    out = capsys.readouterr().out
    assert "safari-cleanup:cache: nothing eligible" in out
    assert "safari-cleanup:favicons: nothing eligible" in out
    assert "safari-cleanup:website-data: nothing eligible" in out


def test_safari_cleanup_running_no_kill_bails(monkeypatch, home_tmp_path, capsys):
    m = load_module()
    monkeypatch.setattr(m, "process_running", lambda name: True)
    cache = home_tmp_path / "cache"
    cache.mkdir()

    m.task_safari_cleanup(m.MODE_DRY_RUN, False, cache, cache, cache)
    out = capsys.readouterr().out
    assert "Safari is running" in out
    assert "nothing eligible" not in out


def test_safari_cleanup_kill_then_clean(monkeypatch, home_tmp_path, capsys):
    m = load_module()
    monkeypatch.setattr(m, "process_running", lambda name: True)
    close_calls = []
    monkeypatch.setattr(m, "close_app", lambda name: close_calls.append(name) or True)

    cache = home_tmp_path / "cache"
    fav = home_tmp_path / "fav"
    web = home_tmp_path / "web"
    for d in (cache, fav, web):
        d.mkdir()

    # Running + --kill-safari + apply: should close Safari, then visit all three targets.
    m.task_safari_cleanup(m.MODE_APPLY, True, cache, fav, web)
    out = capsys.readouterr().out
    assert close_calls == ["Safari"]
    assert "safari-cleanup:cache: nothing eligible" in out
    assert "safari-cleanup:favicons: nothing eligible" in out
    assert "safari-cleanup:website-data: nothing eligible" in out


def test_find_launch_agents_reports_label_and_program(monkeypatch, tmp_path, capsys):
    m = load_module()
    agents = tmp_path / "LaunchAgents"
    agents.mkdir()
    with (agents / "com.example.updater.plist").open("wb") as f:
        m.plistlib.dump(
            {
                "Label": "com.example.updater",
                "ProgramArguments": ["/usr/local/bin/updater", "--daemon"],
                "RunAtLoad": True,
            },
            f,
        )
    monkeypatch.setattr(m, "_launch_agent_loaded", lambda uid, label: False)

    m.task_find_launch_agents(agents)
    out = capsys.readouterr().out
    assert "com.example.updater" in out
    assert "RunAtLoad" in out
    assert "/usr/local/bin/updater" in out


def test_find_launch_agents_survives_nondict_and_missing_fields(monkeypatch, tmp_path, capsys):
    m = load_module()
    agents = tmp_path / "LaunchAgents"
    agents.mkdir()
    # Valid plist whose root is an array, not a dict — must not crash the task.
    with (agents / "com.bad.array.plist").open("wb") as f:
        m.plistlib.dump(["not", "a", "dict"], f)
    # Valid dict plist with no Label, no Program, no ProgramArguments — falls back to stem.
    with (agents / "com.bare.noprogram.plist").open("wb") as f:
        m.plistlib.dump({"RunAtLoad": False}, f)
    monkeypatch.setattr(m, "_launch_agent_loaded", lambda uid, label: False)

    m.task_find_launch_agents(agents)  # must not raise
    out = capsys.readouterr().out
    assert "com.bad.array" in out and "not a dict" in out
    assert "com.bare.noprogram" in out  # label falls back to plist stem


def test_disable_startup_item_dry_run_does_not_call_launchctl(monkeypatch, capsys):
    m = load_module()

    def fail_run(*_a, **_k):
        raise AssertionError("launchctl must not run in dry-run")

    monkeypatch.setattr(m.subprocess, "run", fail_run)
    m._disable_startup_item("com.example.thing", m.MODE_DRY_RUN, "disable-login-item")
    out = capsys.readouterr().out
    assert "would run launchctl disable" in out
    assert "com.example.thing" in out


def test_disable_startup_item_apply_calls_launchctl(monkeypatch, capsys):
    m = load_module()
    calls = []

    def fake_run(argv, **_k):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(m.subprocess, "run", fake_run)
    monkeypatch.setattr(m.os, "getuid", lambda: 501)
    m._disable_startup_item("com.example.thing", m.MODE_APPLY, "disable-launch-agent")
    out = capsys.readouterr().out
    assert calls == [["/bin/launchctl", "disable", "gui/501/com.example.thing"]]
    assert "disabled com.example.thing" in out
    assert "launchctl enable gui/501/com.example.thing" in out


def test_disable_startup_item_apply_logs_failure(monkeypatch, capsys):
    m = load_module()
    monkeypatch.setattr(
        m.subprocess, "run",
        lambda argv, **_k: subprocess.CompletedProcess(argv, 1, stdout="", stderr="boom"),
    )
    m._disable_startup_item("com.example.thing", m.MODE_APPLY, "disable-login-item")
    out = capsys.readouterr().out
    assert "failed to disable com.example.thing: boom" in out


def test_disable_login_item_nothing_to_do(monkeypatch, capsys):
    m = load_module()

    def fail_run(*_a, **_k):
        raise AssertionError("must not touch launchctl when no labels given")

    monkeypatch.setattr(m.subprocess, "run", fail_run)
    m.task_disable_login_item([], m.MODE_APPLY)
    out = capsys.readouterr().out
    assert "nothing to do" in out


def test_disable_launch_agent_nothing_to_do(monkeypatch, capsys):
    m = load_module()

    def fail_run(*_a, **_k):
        raise AssertionError("must not touch launchctl when no labels given")

    monkeypatch.setattr(m.subprocess, "run", fail_run)
    m.task_disable_launch_agent([], m.MODE_APPLY)
    out = capsys.readouterr().out
    assert "nothing to do" in out
