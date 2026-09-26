"""The installer may only change the symlink it owns."""

import os
import subprocess
from pathlib import Path


MANAGE = Path(__file__).resolve().parent.parent / "manage.sh"
SCRIPT = MANAGE.parent / "loopq.py"


def manage(bin_dir, *args):
    return subprocess.run(
        ["bash", str(MANAGE), *args],
        capture_output=True,
        text=True,
        env={**os.environ, "LOOPQ_BIN_DIR": str(bin_dir)},
    )


def test_install_preview_install_and_uninstall(tmp_path):
    bin_dir = tmp_path / "bin"
    link = bin_dir / "loopq"

    preview = manage(bin_dir, "install", "--dry-run")
    assert preview.returncode == 0
    assert str(link) in preview.stdout and str(SCRIPT) in preview.stdout
    assert not link.exists()

    assert manage(bin_dir, "install").returncode == 0
    assert link.is_symlink() and link.resolve() == SCRIPT
    assert manage(bin_dir, "install").returncode == 0

    preview = manage(bin_dir, "uninstall", "--dry-run")
    assert preview.returncode == 0 and link.is_symlink()
    assert manage(bin_dir, "uninstall").returncode == 0
    assert not link.is_symlink()


def test_installer_refuses_an_unrelated_path(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    link = bin_dir / "loopq"
    link.write_text("other command\n")

    assert manage(bin_dir, "install").returncode == 1
    assert manage(bin_dir, "uninstall").returncode == 1
    assert link.read_text() == "other command\n"
