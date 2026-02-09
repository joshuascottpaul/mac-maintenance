import importlib.util
from pathlib import Path

import pytest


def load_module():
    path = Path("/Users/jpaul/Desktop/mac_maintenance/mac_maintenance.py")
    spec = importlib.util.spec_from_file_location("mac_maintenance", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # Ensure module is registered for dataclasses + future annotations
    import sys
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_validate_home_path_ok():
    m = load_module()
    home = Path.home()
    p = home / "Documents"
    assert m.validate_home_path(p, "test") == p.expanduser().resolve()


def test_validate_home_path_rejects_outside():
    m = load_module()
    with pytest.raises(ValueError):
        m.validate_home_path(Path("/etc"), "test")


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


def test_cleanup_archives_dry_run_keeps_files(tmp_path, capsys):
    m = load_module()
    base = Path.home() / ".mac_maintenance_test" / "cleanup_archives"
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


def test_archive_orphans_dry_run_no_delete(tmp_path, capsys):
    m = load_module()
    base = Path.home() / ".mac_maintenance_test" / "archive_orphans"
    base.mkdir(parents=True, exist_ok=True)
    app_support = base / "Application Support"
    app_support.mkdir(parents=True, exist_ok=True)
    folder = app_support / "SomeApp"
    folder.mkdir(exist_ok=True)
    archive_dir = base / "archives"

    m.task_archive_orphans(app_support, archive_dir, ["SomeApp"], 10, m.MODE_DRY_RUN)
    assert folder.exists()
    assert not any(archive_dir.glob("*.zip"))
    out = capsys.readouterr().out
    assert "would archive" in out


def test_brew_maintenance_dry_run_no_brew(monkeypatch, tmp_path, capsys):
    m = load_module()
    # Fake brew binary
    brew = tmp_path / "brew"
    brew.write_text("#!/bin/sh\nexit 0\n")
    brew.chmod(0o755)

    def fail_run(*_args, **_kwargs):
        raise AssertionError("brew should not run in dry-run")

    monkeypatch.setattr(m, "run_brew", fail_run)

    base = Path.home() / ".mac_maintenance_test" / "brew"
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
