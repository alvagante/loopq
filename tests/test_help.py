import os
import subprocess
import sys

from conftest import LOOPQ


def cli(*args):
    return subprocess.run(
        [sys.executable, str(LOOPQ), *args], capture_output=True, text=True,
        env={**os.environ, "LOOPQ_CONFIG_DIR": "/no/such/loops.d"},
    )


def test_help_and_dash_h_show_every_command_without_a_config():
    overview = cli("help")
    short = cli("-h")

    assert overview.returncode == short.returncode == 0
    assert overview.stdout == short.stdout
    for name in ("help", "version", "loops", "create", "doctor", "todo", "status", "milestones",
                 "show", "history", "why", "runs", "session", "add", "tick",
                 "run", "dispatch", "release", "handoff", "retry", "resolve", "ack",
                 "pause", "resume", "cooldown"):
        assert name in overview.stdout
    assert "--loop NAME" in overview.stdout
    assert "--config-dir DIR" in overview.stdout
    assert "-h, --help" in overview.stdout
    assert "list [filters] [--json]" in overview.stdout
    assert "new PATH [options]" in overview.stdout
    assert "list [--state S]" not in overview.stdout
    assert "new PATH [--kind" not in overview.stdout


def test_command_help_matches_dash_h_and_explains_options():
    detailed = cli("help", "tick")
    direct = cli("tick", "-h")

    assert detailed.returncode == direct.returncode == 0
    assert detailed.stdout == direct.stdout
    assert "--agent NAME" in detailed.stdout
    assert "--manual" in detailed.stdout


def test_unknown_help_topic_is_an_error():
    result = cli("help", "missing")

    assert result.returncode == 2
    assert "unknown command 'missing'" in result.stderr


def test_version_works_without_a_config():
    result = cli("version")

    assert result.returncode == 0
    assert result.stdout == "loopq 0.3.0\n"
    assert result.stderr == ""
