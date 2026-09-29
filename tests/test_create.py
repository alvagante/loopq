import os
import subprocess
import sys
from pathlib import Path

import yaml

from conftest import LOOPQ


def invoke(repo, config_dir, *args, path=None):
    env = {**os.environ, "LOOPQ_CONFIG_DIR": str(config_dir)}
    if path is not None:
        env["PATH"] = str(path) + os.pathsep + env["PATH"]
    return subprocess.run([sys.executable, str(LOOPQ), "create", *args],
                          cwd=repo, env=env, capture_output=True, text=True)


def test_create_detects_installed_agents_and_preserves_existing_file(loop):
    config_dir = loop.tmp / "loops.d"
    bin_dir = loop.tmp / "bin"
    bin_dir.mkdir()
    for name in ("claude", "codex", "kiro-cli", "goose", "amp"):
        binary = bin_dir / name
        binary.write_text("#!/bin/sh\n")
        binary.chmod(0o755)

    result = invoke(loop.repo, config_dir, "--project", "my-loop", path=bin_dir)

    assert result.returncode == 0, result.stderr
    config_path = config_dir / "my-loop.yaml"
    config = yaml.safe_load(config_path.read_text())
    assert config["project"] == "my-loop"
    assert config["prefix"] == "my-loop"
    assert config["base"] == "loop-my-loop-base"
    assert config["integration_worktree"] == str(loop.tmp / "my-loop-loop-integration")
    for name in ("claude", "codex", "kiro", "goose", "amp"):
        assert name in config["agents"]
        assert Path(config["agents"][name]["worktree"]).is_absolute()
    assert config["agents"]["codex"]["command"][-1] == "{prompt}"
    assert "command" not in config["agents"]["goose"]
    assert "command" not in config["agents"]["amp"]
    assert "git branch loop-my-loop-base START_REF" in result.stdout
    assert "git worktree add --detach" in result.stdout
    assert "current checkout and branch have not changed" in result.stdout
    assert "ask your coding agent" in result.stdout

    existing = config_path.read_text()
    repeated = invoke(loop.repo, config_dir, "--project", "my-loop", path=bin_dir)
    assert repeated.returncode == 2
    assert config_path.read_text() == existing


def test_create_with_explicit_path_outside_git(tmp_path):
    result = invoke(tmp_path, tmp_path / "configs", str(tmp_path / "loop.yaml"))

    assert result.returncode == 2
    assert "inside a Git repository" in result.stderr
    assert not (tmp_path / "loop.yaml").exists()
