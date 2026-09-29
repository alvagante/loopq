"""The installer may only change the symlink it owns."""

import os
import stat
import subprocess
from pathlib import Path


MANAGE = Path(__file__).resolve().parent.parent / "manage.sh"
SCRIPT = MANAGE.parent / "loopq.py"
SKILL = MANAGE.parent / "skills" / "loopq"


def manage(bin_dir, *args, path=None, env_extra=None):
    env = {**os.environ, "LOOPQ_BIN_DIR": str(bin_dir)}
    if env_extra:
        env.update(env_extra)
    if path is not None:
        # Keep shell utilities; omit the caller's harnesses unless path adds them.
        env["PATH"] = path + os.pathsep + "/usr/bin:/bin"
    return subprocess.run(
        ["bash", str(MANAGE), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def test_install_preview_install_and_uninstall(tmp_path):
    bin_dir = tmp_path / "bin"
    link = bin_dir / "loopq"

    preview = manage(bin_dir, "install", "--dry-run", "--no-skill")
    assert preview.returncode == 0
    assert str(link) in preview.stdout and str(SCRIPT) in preview.stdout
    assert not link.exists()

    assert manage(bin_dir, "install", "--no-skill").returncode == 0
    assert link.is_symlink() and link.resolve() == SCRIPT
    assert manage(bin_dir, "install", "--no-skill").returncode == 0

    preview = manage(bin_dir, "uninstall", "--dry-run")
    assert preview.returncode == 0 and link.is_symlink()
    assert manage(bin_dir, "uninstall").returncode == 0
    assert not link.is_symlink()


def test_installer_refuses_an_unrelated_path(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    link = bin_dir / "loopq"
    link.write_text("other command\n")

    assert manage(bin_dir, "install", "--no-skill").returncode == 1
    assert manage(bin_dir, "uninstall").returncode == 1
    assert link.read_text() == "other command\n"


def _fake_harness(bin_dir: Path, name: str) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    fake = bin_dir / name
    fake.write_text("#!/bin/sh\nexit 0\n")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    return fake


def test_skill_install_symlinks_for_detected_harnesses(tmp_path):
    bin_dir = tmp_path / "bin"
    path_bin = tmp_path / "path"
    home = tmp_path / "home"
    home.mkdir()
    _fake_harness(path_bin, "claude")
    _fake_harness(path_bin, "codex")
    _fake_harness(path_bin, "cursor-agent")
    _fake_harness(path_bin, "agent")  # same Cursor skill dir as cursor-agent

    result = manage(
        bin_dir,
        "install",
        "--skill",
        path=str(path_bin),
        env_extra={"HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config")},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (bin_dir / "loopq").resolve() == SCRIPT

    claude = home / ".claude" / "skills" / "loopq"
    codex = home / ".codex" / "skills" / "loopq"
    cursor = home / ".cursor" / "skills" / "loopq"
    assert claude.is_symlink() and claude.resolve() == SKILL
    assert codex.is_symlink() and codex.resolve() == SKILL
    assert cursor.is_symlink() and cursor.resolve() == SKILL
    assert "Claude Code" in result.stdout and "Codex" in result.stdout
    assert "Cursor" in result.stdout
    assert not (home / ".agents" / "skills" / "loopq").exists()

    again = manage(
        bin_dir,
        "install",
        "--skill",
        path=str(path_bin),
        env_extra={"HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config")},
    )
    assert again.returncode == 0
    assert "already installed" in again.stdout.lower()

    removed = manage(
        bin_dir,
        "uninstall",
        path=str(path_bin),
        env_extra={"HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config")},
    )
    assert removed.returncode == 0
    assert not claude.exists() and not codex.exists() and not cursor.exists()


def test_skill_install_replaces_legacy_loopq_setup_symlink(tmp_path):
    bin_dir = tmp_path / "bin"
    path_bin = tmp_path / "path"
    home = tmp_path / "home"
    _fake_harness(path_bin, "claude")
    legacy = home / ".claude" / "skills" / "loopq-setup"
    legacy.parent.mkdir(parents=True)
    # Point at this checkout's skills tree (old name path need not exist).
    legacy.symlink_to(MANAGE.parent / "skills" / "loopq-setup")

    result = manage(
        bin_dir,
        "install",
        "--skill",
        path=str(path_bin),
        env_extra={"HOME": str(home)},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert not legacy.exists()
    installed = home / ".claude" / "skills" / "loopq"
    assert installed.is_symlink() and installed.resolve() == SKILL
    assert "legacy" in result.stdout.lower()


def test_skill_install_skipped_without_harnesses(tmp_path):
    bin_dir = tmp_path / "bin"
    home = tmp_path / "home"
    home.mkdir()
    result = manage(
        bin_dir,
        "install",
        "--skill",
        path=str(tmp_path / "empty-path"),
        env_extra={"HOME": str(home)},
    )
    assert result.returncode == 0
    assert "No known agent harnesses" in result.stdout
    assert not (home / ".claude" / "skills" / "loopq").exists()


def test_skill_install_refuses_unrelated_skill_path(tmp_path):
    bin_dir = tmp_path / "bin"
    path_bin = tmp_path / "path"
    home = tmp_path / "home"
    _fake_harness(path_bin, "claude")
    other = home / ".claude" / "skills" / "loopq"
    other.parent.mkdir(parents=True)
    other.write_text("not ours\n")

    result = manage(
        bin_dir,
        "install",
        "--skill",
        path=str(path_bin),
        env_extra={"HOME": str(home)},
    )
    assert result.returncode == 1
    assert other.read_text() == "not ours\n"
