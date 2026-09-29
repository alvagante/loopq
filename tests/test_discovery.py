import copy
import json
import os
import subprocess
import sys

import yaml

from conftest import LOOPQ, git


def invoke(loop, config_dir, *args, extra_env=None, cwd=None):
    env = {**os.environ, "LOOPQ_HOME": str(loop.home),
           "LOOPQ_CONFIG_DIR": str(config_dir), **(extra_env or {})}
    if "LOOPQ_LOOP" not in (extra_env or {}):
        env.pop("LOOPQ_LOOP", None)
    return subprocess.run(
        [sys.executable, str(LOOPQ), *args], capture_output=True, text=True,
        env=env, cwd=cwd or loop.tmp,
    )


def two_loops(loop):
    config_dir = loop.tmp / "loops.d"
    config_dir.mkdir()
    (config_dir / "demo.yaml").symlink_to(loop.config_path)
    other = copy.deepcopy(loop.config)
    other["project"] = "other"
    other["integration_worktree"] = str(loop.tmp / "other-int")
    for name, spec in other["agents"].items():
        spec["worktree"] = str(loop.tmp / f"other-{name}")
    (config_dir / "other.yml").write_text(yaml.safe_dump(other))
    return config_dir


def test_saved_default_loop_selects_and_narrows_views(loop):
    config_dir = two_loops(loop)

    assert "no default loop" in invoke(loop, config_dir, "use").stdout
    unknown = invoke(loop, config_dir, "use", "missing")
    assert unknown.returncode == 2 and "unknown loop" in unknown.stderr

    saved = invoke(loop, config_dir, "use", "other")
    assert saved.returncode == 0, saved.stderr
    assert invoke(loop, config_dir, "use").stdout.strip() == "other\t(loopq use)"

    status = invoke(loop, config_dir, "status")
    assert status.returncode == 0, status.stderr
    assert "loopq · demo" not in status.stdout and "other" in status.stdout
    assert "using loop other (loopq use)" in status.stderr

    fragment = loop.tmp / "fragment.md"
    fragment.write_text("---\ntitle: t\nkind: work\ntier: standard\ndeps: []\n---\n## Goal\nx\n")
    added = invoke(loop, config_dir, "add", str(fragment))
    assert added.returncode == 0, added.stderr
    assert list((loop.home / "other" / "ready").glob("*.md"))

    explicit = invoke(loop, config_dir, "status", "--loop", "demo")
    assert "demo" in explicit.stdout and "using loop" not in explicit.stderr

    everything = invoke(loop, config_dir, "status", "--all")
    assert "loopq · demo" in everything.stdout and "loopq · other" in everything.stdout
    assert invoke(loop, config_dir, "status", "--all", "--loop", "demo").returncode == 2

    switched = invoke(loop, config_dir, "use", "--all")
    assert switched.returncode == 0, switched.stderr
    assert "no default loop" in invoke(loop, config_dir, "use").stdout
    for name in ("other-int", "other-a", "other-b"):
        git(loop.repo, "worktree", "add", "-q", "--detach", str(loop.tmp / name), "tools")
    every_loop = invoke(loop, config_dir)
    assert "loopq · demo" in every_loop.stdout and "loopq · other" in every_loop.stdout
    assert "using loop" not in every_loop.stderr
    assert invoke(loop, config_dir, "use", "other").returncode == 0
    assert invoke(loop, config_dir, "use", "other", "--all").returncode == 2
    assert invoke(loop, config_dir, "use").stdout.strip() == "other\t(loopq use)"

    (loop.home / ".current-loop").write_text("gone\n")
    stale = invoke(loop, config_dir, "status")
    assert stale.returncode == 2 and "loopq use --clear" in stale.stderr

    assert invoke(loop, config_dir, "use", "--clear").returncode == 0
    assert not (loop.home / ".current-loop").exists()
    assert "multiple loops found" in invoke(loop, config_dir, "add", str(fragment)).stderr


def test_environment_and_directory_select_before_saved_loop(loop):
    config_dir = two_loops(loop)
    assert invoke(loop, config_dir, "use", "other").returncode == 0

    in_worktree = invoke(loop, config_dir, "use", cwd=loop.wt("a") / ".")
    assert in_worktree.stdout.strip() == "demo\t(current directory)"
    (loop.repo / "sub").mkdir()
    in_repo = invoke(loop, config_dir, "use", cwd=loop.repo / "sub")
    assert in_repo.stdout.strip() == "demo\t(current directory)"

    from_env = invoke(loop, config_dir, "use", cwd=loop.wt("a"),
                      extra_env={"LOOPQ_LOOP": "other"})
    assert from_env.stdout.strip() == "other\t(LOOPQ_LOOP)"

    status = invoke(loop, config_dir, "status", cwd=loop.wt("a"))
    assert status.returncode == 0, status.stderr
    assert "using loop demo (current directory)" in status.stderr

    unknown = invoke(loop, config_dir, "status", extra_env={"LOOPQ_LOOP": "nope"})
    assert unknown.returncode == 2 and "from LOOPQ_LOOP" in unknown.stderr


def test_discovers_loops_and_selects_by_project(loop):
    config_dir = loop.tmp / "loops.d"
    config_dir.mkdir()
    (config_dir / "demo.yaml").symlink_to(loop.config_path)
    other = copy.deepcopy(loop.config)
    other["project"] = "other"
    (config_dir / "other.yml").write_text(yaml.safe_dump(other))

    listed = invoke(loop, config_dir, "loops")
    assert listed.returncode == 0
    assert "demo" in listed.stdout and "other" in listed.stdout

    selected = invoke(loop, config_dir, "status", "--loop", "other")
    assert selected.returncode == 0, selected.stderr
    assert "other" in selected.stdout
    before_command = invoke(loop, config_dir, "--loop", "other", "status",
                            extra_env={"LOOPQ_CONFIG": str(loop.config_path)})
    assert before_command.returncode == 0, before_command.stderr
    assert "other" in before_command.stdout

    all_doctors = invoke(loop, config_dir)
    assert all_doctors.returncode == 0, all_doctors.stderr
    assert "demo" in all_doctors.stdout and "other" in all_doctors.stdout

    all_status = invoke(loop, config_dir, "status")
    assert all_status.returncode == 0, all_status.stderr
    assert "loopq · demo" in all_status.stdout
    assert "loopq · other" in all_status.stdout

    ambiguous = invoke(loop, config_dir, "add", str(loop.tmp / "fragment.md"))
    assert ambiguous.returncode == 2
    assert "multiple loops found" in ambiguous.stderr

    explicit = invoke(loop, config_dir, "status", "--config", str(loop.config_path))
    assert explicit.returncode == 0
    assert "demo" in explicit.stdout


def test_single_discovered_loop_needs_no_config_argument(loop):
    config_dir = loop.tmp / "loops.d"
    config_dir.mkdir()
    (config_dir / "demo.yaml").symlink_to(loop.config_path)

    result = invoke(loop, config_dir, "status")

    assert result.returncode == 0, result.stderr
    assert "demo" in result.stdout


def test_read_views_cover_all_loops_and_fragment_views_find_the_owner(loop):
    config_dir = loop.tmp / "loops.d"
    config_dir.mkdir()
    (config_dir / "demo.yaml").symlink_to(loop.config_path)
    other = copy.deepcopy(loop.config)
    other["project"] = "other"
    other["prefix"] = "ot"
    other["milestones"] = [{"id": "other-start", "source": "manual", "after": [], "hold": False}]
    (config_dir / "other.yml").write_text(yaml.safe_dump(other))
    fragment = loop.add(title="demo task", kind="human")

    for command in ("todo", "milestones"):
        result = invoke(loop, config_dir, command)
        assert result.returncode == 0, result.stderr
        assert "loopq · demo" in result.stdout
        assert "loopq · other" in result.stdout
    assert f"loopq resolve {fragment}" in invoke(loop, config_dir, "todo").stdout
    assert "--loop demo" in invoke(loop, config_dir, "todo").stdout
    assert "other-start" in invoke(loop, config_dir, "milestones").stdout

    cooldown = invoke(loop, config_dir, "cooldown", "--agent", "a")
    assert cooldown.returncode == 0, cooldown.stderr
    assert "loopq · demo" in cooldown.stdout and "loopq · other" in cooldown.stdout

    shown = invoke(loop, config_dir, "show", fragment)
    assert shown.returncode == 0, shown.stderr
    assert "demo task" in shown.stdout
    history = invoke(loop, config_dir, "history", fragment)
    assert history.returncode == 0, history.stderr
    assert "demo task" in history.stdout

    other_fragment = loop.home / "other" / "human" / f"{fragment}.md"
    other_fragment.parent.mkdir(parents=True, exist_ok=True)
    other_fragment.write_text((loop.queue / "human" / f"{fragment}.md").read_text())
    duplicate = invoke(loop, config_dir, "show", fragment)
    assert duplicate.returncode == 2
    assert "matches 2 loops" in duplicate.stderr
    other_fragment.unlink()

    for project in ("demo", "other"):
        event_path = loop.home / project / "logs" / "events.jsonl"
        event_path.parent.mkdir(parents=True, exist_ok=True)
        event = {"ts": "2026-09-25T10:00:00+00:00", "event": "claimed",
                 "id": f"{project}-1", "agent": "a", "to": "claimed", "detail": ""}
        with event_path.open("a") as output:
            output.write(json.dumps(event) + "\n")
    runs = invoke(loop, config_dir, "runs", "--limit", "1")
    assert runs.returncode == 0, runs.stderr
    assert "Loop" in runs.stdout
    assert sum(f"{project}-1" in runs.stdout for project in ("demo", "other")) == 1
