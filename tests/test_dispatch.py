import copy
import json
import os
import subprocess
import sys
import time

import yaml

from conftest import LOOPQ, git


AGENT = [
    "sh", "-c",
    "echo hello > work.txt; printf '%s\\n' '---' 'status: done' "
    "'commit: \"feat: dispatched\"' '---' 'done' > .loop/RESULT.md",
]


def invoke(loop, *args, extra_env=None):
    return subprocess.run(
        [sys.executable, str(LOOPQ), *args], capture_output=True, text=True,
        env={**os.environ, "LOOPQ_HOME": str(loop.home), "LOOPQ_NOW": loop.now,
             **(extra_env or {})},
    )


def test_dispatch_starts_agents_across_loops(loop):
    loop.config["agents"]["a"]["command"] = AGENT
    loop.save_config()
    first = loop.add(title="first")

    second_repo = loop.tmp / "second-repo"
    git(loop.tmp, "clone", "-q", str(loop.repo), str(second_repo))
    git(second_repo, "config", "user.email", "t@example.invalid")
    git(second_repo, "config", "user.name", "Test")
    git(second_repo, "branch", "tools", "origin/tools")
    for name in ("a", "b", "int"):
        git(second_repo, "worktree", "add", "-q", "--detach",
            str(loop.tmp / f"second-wt-{name}"), "tools")
    other = copy.deepcopy(loop.config)
    other["project"] = "second"
    other["prefix"] = "sc"
    other["integration_worktree"] = str(loop.tmp / "second-wt-int")
    for name in ("a", "b"):
        other["agents"][name]["worktree"] = str(loop.tmp / f"second-wt-{name}")

    config_dir = loop.tmp / "loops.d"
    config_dir.mkdir()
    (config_dir / "first.yaml").write_text(yaml.safe_dump(loop.config))
    other_config = config_dir / "second.yml"
    other_config.write_text(yaml.safe_dump(other))
    fragment = loop.tmp / "other-fragment.md"
    fragment.write_text("---\ntitle: second\nkind: work\ntier: standard\n---\n## Goal\nDo it.\n")
    assert invoke(loop, "add", str(fragment), "--config", str(other_config)).returncode == 0

    preview = invoke(loop, "dispatch", "--config-dir", str(config_dir), "--dry-run")
    assert preview.returncode == 0, preview.stderr
    assert "would start demo/a" in preview.stdout
    assert "would start second/a" in preview.stdout
    assert "skip demo/b: no command" in preview.stdout
    assert "skip second/b: no command" in preview.stdout
    assert not (loop.queue / "logs" / "dispatch-a.log").exists()

    result = invoke(loop, "dispatch", "--config-dir", str(config_dir))
    assert result.returncode == 0, result.stderr
    assert "started demo/a" in result.stdout
    assert "started second/a" in result.stdout

    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if loop.state_of(first) == "review" and list((loop.home / "second" / "review").glob("*.md")):
            break
        time.sleep(0.05)
    assert loop.state_of(first) == "review"
    assert list((loop.home / "second" / "review").glob("*.md"))


def test_dispatch_reports_missing_directory(loop):
    result = invoke(loop, "dispatch", "--config-dir", str(loop.tmp / "missing"))
    assert result.returncode == 2
    assert "config directory does not exist" in result.stderr


def test_dispatch_continues_after_invalid_config(loop):
    config_dir = loop.tmp / "loops.d"
    config_dir.mkdir()
    (config_dir / "bad.yaml").write_text("agents: [not-a-mapping]\n")
    loop.config["agents"]["a"]["command"] = AGENT
    (config_dir / "good.yml").write_text(yaml.safe_dump(loop.config))

    result = invoke(loop, "dispatch", "--config-dir", str(config_dir), "--dry-run")

    assert result.returncode == 1
    assert "bad.yaml" in result.stderr
    assert "would start demo/a" in result.stdout


def test_orca_dispatch_respects_schedule_and_rejects_enabled_automation(loop):
    config_dir = loop.tmp / "loops.d"
    config_dir.mkdir()
    config = config_dir / "loop.yaml"
    loop.config["agents"]["a"]["launcher"] = "orca"
    loop.config["agents"]["a"]["cron"] = "0,20,40 * * * *"
    config.write_text(yaml.safe_dump(loop.config))

    automation = {"id": "orca-a", "enabled": True, "rrule": "0,20,40 * * * *",
                  "precheck": {"command": f"loopq tick --agent a --config {config}"}}
    listing = loop.tmp / "automations.json"
    listing.write_text(json.dumps({"ok": True, "result": {"automations": [automation]}}))
    calls = loop.tmp / "calls"
    fake_orca = loop.tmp / "orca"
    fake_orca.write_text(
        "#!/bin/sh\n"
        "if [ \"$2\" = list ]; then cat \"$FAKE_AUTOMATIONS\"; exit; fi\n"
        "printf '%s\\n' \"$3\" >> \"$FAKE_RUNS\"\n"
        "printf '{\"ok\":true}\n'\n"
    )
    fake_orca.chmod(0o755)
    env = {"LOOPQ_ORCA_CLI": str(fake_orca), "FAKE_AUTOMATIONS": str(listing),
           "FAKE_RUNS": str(calls)}

    preview = invoke(loop, "dispatch", "--config-dir", str(config_dir), "--dry-run",
                     extra_env=env)
    assert "would trigger demo/a" in preview.stdout
    assert "enabled in Orca" in preview.stdout
    refused = invoke(loop, "dispatch", "--config-dir", str(config_dir), extra_env=env)
    assert refused.returncode == 1
    assert "disable Orca automation" in refused.stderr
    assert not calls.exists()

    automation["enabled"] = False
    listing.write_text(json.dumps({"ok": True, "result": {"automations": [automation]}}))
    started = invoke(loop, "dispatch", "--config-dir", str(config_dir), extra_env=env)
    assert started.returncode == 0, started.stderr
    assert "triggered demo/a" in started.stdout
    assert calls.read_text().splitlines() == ["orca-a"]

    again = invoke(loop, "dispatch", "--config-dir", str(config_dir), extra_env=env)
    assert again.returncode == 0
    assert calls.read_text().splitlines() == ["orca-a"]

    later = invoke(loop, "dispatch", "--config-dir", str(config_dir),
                   extra_env={**env, "LOOPQ_NOW": "2026-09-25T10:01:00+00:00"})
    assert later.returncode == 0
    assert calls.read_text().splitlines() == ["orca-a"]
