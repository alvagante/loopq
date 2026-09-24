"""Test harness: a temporary project repository with agent worktrees, a queue
root and a loop.yaml, driven only through the loopq command line."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

LOOPQ = Path(__file__).resolve().parent.parent / "loopq.py"


def git(cwd, *args, check=True):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=check, capture_output=True, text=True
    )


class Loop:
    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.home = tmp / "home"
        self.repo = tmp / "repo"
        self.notify_log = tmp / "notify.log"
        self.now = "2026-09-25T10:00:00+00:00"
        self.config_path = tmp / "loop.yaml"
        self.config = {}

    # queue inspection -------------------------------------------------
    @property
    def queue(self) -> Path:
        return self.home / "demo"

    def state_of(self, fid):
        hits = [p.parent.name for p in self.queue.glob(f"*/{fid}.md")]
        assert len(hits) <= 1, hits
        return hits[0] if hits else None

    def fragment(self, fid):
        path = next(self.queue.glob(f"*/{fid}.md"))
        text = path.read_text()
        _, front, body = text.split("---\n", 2)
        return yaml.safe_load(front), body

    def ids_in(self, state):
        return sorted(p.stem for p in (self.queue / state).glob("*.md"))

    def notifications(self):
        if not self.notify_log.exists():
            return []
        return self.notify_log.read_text().splitlines()

    # worktrees ----------------------------------------------------------
    def wt(self, agent) -> Path:
        return self.tmp / f"wt-{agent}"

    def write_result(self, agent, status="done", verdict=None, commit=None, body="ok"):
        front = {"status": status, "verdict": verdict, "commit": commit}
        path = self.wt(agent) / ".loop" / "RESULT.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("---\n" + yaml.safe_dump(front) + "---\n" + body + "\n")

    def base_log(self):
        return git(self.repo, "log", "--format=%s%n%b", "tools").stdout

    # command line -------------------------------------------------------
    def save_config(self):
        self.config_path.write_text(yaml.safe_dump(self.config, sort_keys=False))

    def run(self, *args, now=None):
        env = dict(os.environ)
        env["LOOPQ_HOME"] = str(self.home)
        env["LOOPQ_NOW"] = now or self.now
        return subprocess.run(
            [sys.executable, str(LOOPQ), *args, "--config", str(self.config_path)],
            capture_output=True,
            text=True,
            env=env,
        )

    def tick(self, agent, *extra, now=None):
        return self.run("tick", "--agent", agent, *extra, now=now)

    def add(self, **front):
        body = front.pop("body", "## Goal\nDo it.\n## Acceptance\nIt is done.\n")
        front.setdefault("kind", "work")
        front.setdefault("tier", "standard")
        front.setdefault("deps", [])
        path = self.tmp / f"new-{front['title'].replace(' ', '-')}.md"
        path.write_text("---\n" + yaml.safe_dump(front) + "---\n" + body)
        res = self.run("add", str(path))
        assert res.returncode == 0, res.stderr
        return res.stdout.strip()


@pytest.fixture
def loop(tmp_path):
    lp = Loop(tmp_path)
    repo = lp.repo
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "t@example.invalid")
    git(repo, "config", "user.name", "Test")
    (repo / ".gitignore").write_text(".loop/\n")
    (repo / "app.txt").write_text("line one\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "init")
    git(repo, "branch", "tools")
    for name in ("a", "b", "int"):
        git(repo, "worktree", "add", "-q", "--detach", str(lp.wt(name)), "tools")
    lp.config = {
        "project": "demo",
        "prefix": "tb",
        "base": "tools",
        "repo": str(repo),
        "integration_worktree": str(lp.wt("int")),
        "lease": "4h",
        "gate": ["! grep -rq FAIL --include=*.txt ."],
        "forbid_chars": ["—"],
        "notify": ["sh", "-c", f'printf "%s\\n" "$1" >> {lp.notify_log}', "notify"],
        "preamble": "Project rules go here.",
        "milestones": [],
        "agents": {
            "a": {
                "worktree": str(lp.wt("a")),
                "tiers": ["judgement", "standard", "mechanical"],
                "kinds": ["work", "review", "conflict", "decompose", "brief"],
                "limit_cooldown": "2h",
            },
            "b": {
                "worktree": str(lp.wt("b")),
                "tiers": ["judgement", "standard", "mechanical"],
                "kinds": ["work", "review", "conflict", "decompose", "brief"],
                "limit_cooldown": "2h",
            },
        },
    }
    lp.save_config()
    return lp
