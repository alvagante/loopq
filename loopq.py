#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml==6.0.3", "rich==15.0.0"]
# ///
"""loopq: a local fragment queue that lets several agent budgets pull
session-sized work, with gates, cross-agent review and integration done by
this script. See the fragment loop spec for the contract."""

import argparse
import datetime as dt
import fcntl
import glob
import json
import os
import re
import shlex
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

import yaml
from rich import box
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

STATES = ("ready", "claimed", "review", "human", "done")
KIND_ORDER = ("conflict", "review", "work", "decompose", "brief")

RESULT_SPEC = """\
## When you finish

Write `.loop/RESULT.md` in this worktree, and nothing outside the worktree:

```markdown
---
status: done          # done | blocked | parked
verdict: null         # review only: approve | changes
commit: "type(scope): summary"   # work and conflict only
---
What you did, the commands you ran and their result lines, open questions
(blocked), numbered findings (review), or the brief (brief).
```

Do not commit, push, open pull requests, publish, or set secrets.
"""

TEMPLATES = {
    "work": (
        "Do this fragment in the current worktree. Read the files under Read "
        "first. Change only the files it names. Run its Acceptance commands. "
        "If you cannot finish, write status `parked` with the exact next step, "
        "or `blocked` with the question for the operator."
    ),
    "conflict": (
        "The fragment's branch no longer applies cleanly to `{base}`. This "
        "worktree holds its changes squashed onto `{base}`, with conflict "
        "markers. Resolve every conflict keeping the intent of both sides, "
        "run the Acceptance commands, and report."
    ),
    "review": (
        "Review the diff `{base}...HEAD` against the fragment's Goal, "
        "Acceptance and Read first. Re-run the Acceptance commands. Do not "
        "edit files. Verdict `approve`, or `changes` with numbered blocking "
        "findings. A finding is blocking only when the diff fails the "
        "fragment's Goal or Acceptance, breaks something that worked, or "
        "contradicts a document under Read first. A new requirement, a "
        "hardening idea or a problem in unchanged code is outside the "
        "fragment's Goal and Acceptance: list it under a `Follow-ups` "
        "heading, where it never changes the verdict."
    ),
    "decompose": (
        "Read `{source}` and the documents it names. Write this milestone's "
        "fragments to `.loop/out/fragments/<name>.md`, each fitting one short "
        "agent session, in the fragment format below, with `title`, `kind` "
        "(`work`, or `human` for steps only the operator can take), `tier` "
        "(`judgement`, `standard` or `mechanical`), `deps` (existing ids or "
        "the `<name>` of another file in this batch), and the sections Goal, "
        "Read first, Files and Acceptance. Change no other file."
    ),
    "brief": (
        "Milestone `{milestone}` is complete. Read its finished fragments "
        "listed below and write, as the RESULT body, a brief of at most 15 "
        "lines: what it produced; the evidence (gates, review verdicts, "
        "commands); decisions no ADR settled; risks; open human items."
    ),
}


# time -------------------------------------------------------------------

def now():
    raw = os.environ.get("LOOPQ_NOW")
    if raw:
        return dt.datetime.fromisoformat(raw)
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def parse_duration(text):
    m = re.fullmatch(r"(\d+)([smhd])", str(text).strip())
    if not m:
        raise SystemExit(f"loopq: bad duration {text!r}")
    unit = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}[m.group(2)]
    return dt.timedelta(**{unit: int(m.group(1))})


# git --------------------------------------------------------------------

class GitError(Exception):
    pass


def git(cwd, *args, check=True):
    res = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and res.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed in {cwd}:\n{(res.stdout + res.stderr).strip()}")
    return res


def branch_exists(repo, branch):
    return git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", check=False).returncode == 0


# fragments --------------------------------------------------------------

class Fragment:
    def __init__(self, path, front, body):
        self.path = Path(path)
        self.front = front
        self.body = body

    @classmethod
    def read(cls, path):
        text = Path(path).read_text()
        if not text.startswith("---\n"):
            raise ValueError(f"{path}: missing front matter")
        _, front, body = text.split("---\n", 2)
        return cls(path, yaml.safe_load(front) or {}, body)

    @property
    def id(self):
        return self.front["id"]

    @property
    def state(self):
        return self.path.parent.name

    def text(self):
        return "---\n" + yaml.safe_dump(self.front, sort_keys=False) + "---\n" + self.body

    def save(self):
        self.path.write_text(self.text())

    def note(self, text):
        if "## Notes" not in self.body:
            self.body = self.body.rstrip("\n") + "\n## Notes\n"
        self.body = self.body.rstrip("\n") + f"\n- {now().isoformat()}: {text}\n"


class Queue:
    def __init__(self, cfg):
        home = Path(os.environ.get("LOOPQ_HOME") or Path.home() / ".loops")
        self.cfg = cfg
        self.root = home / cfg["project"]
        self.actor = "operator"
        for d in (*STATES, "briefs", "logs", "cooldown", "acks", "ticks"):
            (self.root / d).mkdir(parents=True, exist_ok=True)

    def event(self, event, fid=None, agent=None, to=None, detail=""):
        rec = {"ts": now().isoformat(), "event": event, "id": fid,
               "agent": agent or self.actor, "to": to, "detail": detail}
        with open(self.root / "logs" / "events.jsonl", "a") as fh:
            fh.write(json.dumps(rec) + "\n")

    def events(self):
        path = self.root / "logs" / "events.jsonl"
        if not path.exists():
            return []
        return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]

    @contextmanager
    def locked(self):
        with open(self.root / ".lock", "w") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    def all(self, state=None):
        states = [state] if state else STATES
        out = []
        for s in states:
            out += [Fragment.read(p) for p in sorted((self.root / s).glob("*.md"))]
        return out

    def get(self, fid):
        for s in STATES:
            p = self.root / s / f"{fid}.md"
            if p.exists():
                return Fragment.read(p)
        return None

    def move(self, frag, state, why="moved", agent=None, detail=""):
        dest = self.root / state / frag.path.name
        if state == "human" and frag.front.get("kind") != "human":
            frag.front["notified"] = True  # the caller notifies
        frag.save()
        os.rename(frag.path, dest)
        frag.path = dest
        self.event(why, frag.id, agent, state, detail)

    def next_id(self):
        counter = self.root / "next_id"
        n = int(counter.read_text()) if counter.exists() else 1
        counter.write_text(str(n + 1))
        return f"{self.cfg['prefix']}-{n:04d}"

    def create(self, front, body, state=None):
        front = {k: v for k, v in dict(front).items() if k != "id"}
        front.setdefault("deps", [])
        front.setdefault("attempts", 0)
        front.setdefault("claimed_by", None)
        front.setdefault("lease_until", None)
        if front.get("kind") == "human":
            front.setdefault("notified", False)
        state = state or ("human" if front.get("kind") == "human" else "ready")
        ordered = {"id": self.next_id(), **front}
        frag = Fragment(self.root / state / f"{ordered['id']}.md", ordered, body)
        frag.save()
        self.event("created", frag.id, to=state, detail=front.get("title", ""))
        return frag

    def done_ids(self):
        return {p.stem for p in (self.root / "done").glob("*.md")}


# selection --------------------------------------------------------------

def milestone_rank(cfg, milestone):
    ids = [m["id"] for m in cfg.get("milestones") or []]
    return ids.index(milestone) if milestone in ids else len(ids)


def eligible(cfg, agent_name, frag, done):
    agent = cfg["agents"][agent_name]
    f = frag.front
    if f.get("kind") not in agent.get("kinds", []):
        return False
    if f.get("tier") not in agent.get("tiers", []):
        return False
    if any(d not in done for d in f.get("deps") or []):
        return False
    if f.get("kind") == "review" and f.get("author") == agent_name:
        return False
    return True


def pick(q, agent_name):
    done = q.done_ids()
    cands = [f for f in q.all("ready") if eligible(q.cfg, agent_name, f, done)]
    cands.sort(key=lambda f: (
        KIND_ORDER.index(f.front["kind"]) if f.front["kind"] in KIND_ORDER else 99,
        milestone_rank(q.cfg, f.front.get("milestone")),
        f.id,
    ))
    return cands[0] if cands else None


# worktree preparation ---------------------------------------------------

def loop_dir(worktree):
    return Path(worktree) / ".loop"


def clear_loop_dir(worktree):
    d = loop_dir(worktree)
    if d.exists():
        for p in sorted(d.rglob("*"), reverse=True):
            p.unlink() if p.is_file() else p.rmdir()
        d.rmdir()


def worktree_clean(worktree):
    return git(worktree, "status", "--porcelain").stdout.strip() == ""


def render(q, frag):
    cfg = q.cfg
    kind = frag.front["kind"]
    templates = {**TEMPLATES, **(cfg.get("templates") or {})}
    source = ""
    for m in cfg.get("milestones") or []:
        if m["id"] == frag.front.get("milestone"):
            source = m.get("source", "")
    task = templates[kind].format(
        base=cfg["base"], source=source, milestone=frag.front.get("milestone")
    )
    parts = [cfg.get("preamble", "").strip(), f"## Your task ({kind})\n\n{task}", RESULT_SPEC]
    if kind == "brief":
        listing = "\n".join(
            f"- {f.path}" for f in q.all("done")
            if f.front.get("milestone") == frag.front.get("milestone")
        )
        parts.append("## Finished fragments\n\n" + listing)
    parts.append("## Fragment\n\n" + frag.text())
    return "\n\n".join(p for p in parts if p) + "\n"


def prepare(q, agent_name, frag):
    cfg = q.cfg
    wt = cfg["agents"][agent_name]["worktree"]
    clear_loop_dir(wt)
    if not worktree_clean(wt):
        return False
    kind = frag.front["kind"]
    if kind == "work":
        branch = frag.front.get("branch") or f"loop/{frag.id}"
        frag.front["branch"] = branch
        if branch_exists(wt, branch):
            git(wt, "checkout", "-q", branch)
        else:
            git(wt, "checkout", "-q", "-b", branch, cfg["base"])
    elif kind == "review":
        git(wt, "checkout", "-q", "--detach", frag.front["branch"])
    elif kind == "conflict":
        git(wt, "checkout", "-q", "--detach", cfg["base"])
        git(wt, "merge", "--squash", frag.front["branch"], check=False)
    else:
        git(wt, "checkout", "-q", "--detach", cfg["base"])
    d = loop_dir(wt)
    d.mkdir(exist_ok=True)
    (d / "FRAGMENT.md").write_text(render(q, frag))
    return True


# gate -------------------------------------------------------------------

def run_gate(cfg, worktree):
    """Return None when the gate passes, else the failure text."""
    base = cfg["base"]
    for cmd in cfg.get("gate") or []:
        res = subprocess.run(
            cmd.format(base=base), shell=True, cwd=worktree, capture_output=True, text=True
        )
        if res.returncode != 0:
            out = (res.stdout + res.stderr).strip()[-2000:]
            return f"gate command failed: {cmd}\n{out}"
    forbid = cfg.get("forbid_chars") or []
    if forbid:
        diff = git(worktree, "diff", f"{base}...HEAD").stdout
        added = [l for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++")]
        bad = [l for l in added if any(c in l for c in forbid)]
        if bad:
            return "forbidden characters in added lines:\n" + "\n".join(bad[:10])
    return None


# collect ----------------------------------------------------------------

def read_result(worktree):
    path = loop_dir(worktree) / "RESULT.md"
    if not path.exists():
        return None
    try:
        res = Fragment.read(path)
        if not isinstance(res.front, dict):
            raise ValueError("front matter is not a mapping")
    except (ValueError, yaml.YAMLError) as err:
        text = path.read_text(errors="replace")
        return {"status": "blocked"}, f"loopq could not parse RESULT.md ({err}):\n{text}"
    return res.front, res.body


def commit_all(worktree, message, frag_id, agent):
    git(worktree, "add", "-A")
    if git(worktree, "diff", "--cached", "--quiet", check=False).returncode == 0:
        return False
    msg = f"{message}\n\nLoop-Fragment: {frag_id}\nLoop-Agent: {agent}\n"
    git(worktree, "commit", "-q", "-m", msg)
    return True


def discard(worktree):
    git(worktree, "reset", "-q", "--hard")
    git(worktree, "clean", "-q", "-fd")


def release(frag):
    frag.front["claimed_by"] = None
    frag.front["lease_until"] = None


def collect(q, agent):
    wt = q.cfg["agents"][agent]["worktree"]
    held = [f for f in q.all("claimed") if f.front.get("claimed_by") == agent]
    if not held:
        return "free"
    frag = held[0]
    result = read_result(wt)
    if result is None:
        if dt.datetime.fromisoformat(frag.front["lease_until"]) > now():
            return "busy"
        safe_expire(q, frag)
        start_cooldown(q, agent)
        return "free"
    front, body = result
    outs = [Fragment.read(p) for p in sorted((loop_dir(wt) / "out" / "fragments").glob("*.md"))]
    try:
        transition(q, agent, wt, frag, front, body, outs)
    except GitError as err:
        to_human_on_error(q, agent, [frag.id, frag.front.get("target")], err, body)
    clear_loop_dir(wt)
    git(wt, "checkout", "-q", "--detach", check=False)
    return "free"


def to_human_on_error(q, agent, ids, err, body=""):
    """A git or hook failure while handling a fragment: stop and ask."""
    iw = q.cfg["integration_worktree"]
    git(iw, "rebase", "--abort", check=False)
    git(iw, "checkout", "-q", "--detach", check=False)
    for fid in [i for i in ids if i]:
        frag = q.get(fid)
        if frag is None or frag.state in ("done", "human"):
            continue
        release(frag)
        frag.note(f"loopq hit an error handling this for {agent}; the worktree is "
                  f"left as it was.\n{err}\nAgent result:\n{body.strip()}")
        q.move(frag, "human", "error", agent)
        notify(q.cfg, f"{fid} needs you: git error while handling it")


def transition(q, agent, wt, frag, front, body, outs):
    kind = frag.front["kind"]
    release(frag)
    if kind == "work":
        collect_work(q, agent, wt, frag, front, body)
    elif kind == "review":
        collect_review(q, agent, wt, frag, front, body)
    elif kind == "conflict":
        collect_conflict(q, agent, wt, frag, front, body)
    elif kind == "decompose":
        collect_decompose(q, agent, wt, frag, front, body, outs)
    elif kind == "brief":
        collect_brief(q, agent, wt, frag, front, body)


def expire(q, frag):
    """A claim whose lease ran out without a result: keep partial work."""
    agent = frag.front["claimed_by"]
    wt = q.cfg["agents"][agent]["worktree"]
    clear_loop_dir(wt)
    kind = frag.front["kind"]
    if kind in ("work", "conflict"):
        commit_all(wt, f"wip({frag.id}): partial", frag.id, agent)
    else:
        discard(wt)
    git(wt, "checkout", "-q", "--detach")
    release(frag)
    frag.note(f"lease of {agent} expired without a result")
    q.move(frag, "ready", "expired", agent)


def safe_expire(q, frag):
    agent = frag.front["claimed_by"]
    try:
        expire(q, frag)
    except GitError as err:
        to_human_on_error(q, agent, [frag.id], err)


def expire_others(q, agent):
    for frag in q.all("claimed"):
        other = frag.front.get("claimed_by")
        if other == agent:
            continue
        if dt.datetime.fromisoformat(frag.front["lease_until"]) <= now():
            if read_result(q.cfg["agents"][other]["worktree"]) is not None:
                collect(q, other)  # finished late: keep the result
            else:
                safe_expire(q, frag)


def promote_humans(q):
    """Notify a human step once, when every dep is done."""
    done = q.done_ids()
    for frag in q.all("human"):
        pending_notice = frag.front.get("notified") is False or (
            "notified" not in frag.front and frag.front.get("kind") == "human")
        if pending_notice and all(d in done for d in frag.front.get("deps") or []):
            frag.front["notified"] = True
            frag.save()
            notify(q.cfg, f"{frag.id} needs you: {frag.front.get('title', '')}")


def review_body(target):
    """The review stub plus the target's own spec, so the reviewer judges
    against the same Goal, Files and Acceptance the author worked to."""
    spec = target.body.split("## Notes")[0].strip()
    return (f"## Goal\nReview {target.id} against its spec below.\n\n"
            f"## Spec of {target.id}\n\n{spec}\n")


def collect_work(q, agent, wt, frag, front, body):
    status = front.get("status")
    message = front.get("commit") or f"wip({frag.id}): {frag.front.get('title', '')}"
    commit_all(wt, message, frag.id, agent)
    frag.front["last_agent"] = agent
    if status == "done":
        failure = run_gate(q.cfg, wt)
        if failure is None:
            q.move(frag, "review", "gate-passed", agent)
            q.create({
                "title": f"Review {frag.id}: {frag.front.get('title', '')}",
                "kind": "review",
                "tier": frag.front.get("tier"),
                "milestone": frag.front.get("milestone"),
                "target": frag.id,
                "author": agent,
                "branch": frag.front["branch"],
            }, review_body(frag))
            return
        send_back(q, frag, failure, why="gate-failed", agent=agent)
    elif status == "blocked":
        frag.note(f"blocked ({agent}):\n{body.strip()}")
        q.move(frag, "human", "blocked", agent)
        notify(q.cfg, f"{frag.id} is blocked: {frag.front.get('title', '')}")
    else:  # parked
        frag.note(f"parked by {agent}:\n{body.strip()}")
        q.move(frag, "ready", "parked", agent)
        start_cooldown(q, agent)


def notify(cfg, message):
    cmd = cfg.get("notify")
    if cmd is None:
        safe = message.replace('"', "'")
        cmd = ["osascript", "-e", f'display notification "{safe}" with title "loopq"']
        subprocess.run(cmd, capture_output=True)
        return
    subprocess.run([*cmd, message], capture_output=True)


def send_back(q, frag, reason, max_attempts=3, why="sent-back", agent=None):
    frag.front["attempts"] = int(frag.front.get("attempts") or 0) + 1
    frag.note(reason)
    release(frag)
    if frag.front["attempts"] >= max_attempts:
        q.move(frag, "human", "gave-up", agent, why)
        notify(q.cfg, f"{frag.id} needs you after {frag.front['attempts']} attempts")
    else:
        q.move(frag, "ready", why, agent)


def start_cooldown(q, agent):
    spec = q.cfg["agents"][agent]
    until = now() + parse_duration(spec.get("limit_cooldown", "2h"))
    (q.root / "cooldown" / agent).write_text(until.isoformat())
    if spec.get("cooldown_notice"):
        notify(q.cfg, spec["cooldown_notice"])


def in_cooldown(q, agent):
    path = q.root / "cooldown" / agent
    if not path.exists():
        return False
    return dt.datetime.fromisoformat(path.read_text().strip()) > now()


def collect_review(q, agent, wt, frag, front, body):
    discard(wt)
    target = q.get(frag.front["target"])
    frag.note(f"verdict {front.get('verdict')} by {agent}")
    q.move(frag, "done", "reviewed", agent, str(front.get("verdict")))
    if front.get("status") != "done":
        send_back(q, target, f"review by {agent} did not finish: {body.strip()}", why="review-unfinished", agent=agent)
        return
    if front.get("verdict") == "approve":
        integrate(q, target)
    else:
        send_back(q, target, f"review by {agent} asked for changes:\n{body.strip()}", why="changes-asked", agent=agent)


def collect_conflict(q, agent, wt, frag, front, body):
    target = q.get(frag.front["target"])
    if front.get("status") != "done":
        discard(wt)
        frag.note(f"{front.get('status')} by {agent}:\n{body.strip()}")
        if front.get("status") == "parked":
            q.move(frag, "ready", "parked", agent)
            start_cooldown(q, agent)
        else:
            q.move(frag, "human", "blocked", agent)
            notify(q.cfg, f"{frag.id} is blocked: {frag.front.get('title', '')}")
        return
    message = front.get("commit") or target.front.get("title", frag.id)
    commit_all(wt, message, target.id, agent)
    git(wt, "branch", "-f", frag.front["branch"], "HEAD")
    frag.note(f"resolved by {agent}")
    q.move(frag, "done", "resolved-conflict", agent)
    integrate(q, target)


def all_ids(q):
    return {p.stem for s in STATES for p in (q.root / s).glob("*.md")}


def validate_batch(q, outs):
    names = {o.path.stem for o in outs}
    known = all_ids(q)
    errors = []
    for o in outs:
        f, name = o.front, o.path.name
        if not f.get("title"):
            errors.append(f"{name}: missing title")
        if f.get("kind") not in ("work", "human"):
            errors.append(f"{name}: kind must be work or human")
        if f.get("tier") not in ("judgement", "standard", "mechanical"):
            errors.append(f"{name}: missing or unknown tier")
        deps = f.get("deps")
        if not isinstance(deps, list):
            errors.append(f"{name}: deps must be a list")
            continue
        for d in deps:
            if d not in names and d not in known:
                errors.append(f"{name}: unknown dep {d}")
        if f.get("kind") == "work":
            for section in ("## Goal", "## Acceptance"):
                if section not in o.body:
                    errors.append(f"{name}: missing section {section}")
    if not outs:
        errors.append("no fragments written to .loop/out/fragments/")
    return errors


def collect_decompose(q, agent, wt, frag, front, body, outs):
    discard(wt)
    if front.get("status") != "done":
        send_back(q, frag, f"{front.get('status')} by {agent}:\n{body.strip()}", why=str(front.get("status")), agent=agent)
        return
    errors = validate_batch(q, outs)
    if errors:
        send_back(q, frag, "invalid decomposition:\n" + "\n".join(errors), why="invalid-output", agent=agent)
        return
    ids = {}
    for o in outs:
        ids[o.path.stem] = q.next_id()
    for o in outs:
        fr = {k: v for k, v in o.front.items() if k != "id"}
        fr["deps"] = [ids.get(d, d) for d in fr["deps"]]
        fr["milestone"] = fr.get("milestone") or frag.front.get("milestone")
        state = "human" if fr["kind"] == "human" else "ready"
        extra = {"notified": False} if state == "human" else {}
        new = Fragment(q.root / state / f"{ids[o.path.stem]}.md",
                       {"id": ids[o.path.stem], "attempts": 0, "claimed_by": None,
                        "lease_until": None, **fr, **extra}, o.body)
        new.save()
        q.event("created", new.id, to=state, detail=fr.get("title", ""))
    frag.note(f"decomposed by {agent} into {', '.join(ids.values())}")
    q.move(frag, "done", "decomposed", agent)


def collect_brief(q, agent, wt, frag, front, body):
    discard(wt)
    if front.get("status") != "done":
        send_back(q, frag, f"{front.get('status')} by {agent}:\n{body.strip()}", why=str(front.get("status")), agent=agent)
        return
    mid = frag.front.get("milestone")
    path = q.root / "briefs" / f"{mid}.md"
    path.write_text(body.strip() + "\n")
    q.move(frag, "done", "briefed", agent)
    notify(q.cfg, f"brief for {mid} is ready: {path}")
    follow = q.cfg.get("brief_followup")
    if follow:
        q.create({
            "title": follow["title"],
            "kind": "work",
            "tier": follow.get("tier", "mechanical"),
            "milestone": mid,
        }, f"## Goal\n{follow.get('goal', '')}\n## Read first\n{path}\n"
           f"## Acceptance\nThe brief is recorded as the goal says.\n")


# milestones -------------------------------------------------------------

def milestone_complete(q, mid):
    frags = [f for f in q.all() if f.front.get("milestone") == mid and f.front["kind"] != "brief"]
    has_dec = any(f.front["kind"] == "decompose" for f in frags)
    return has_dec and all(f.state == "done" for f in frags)


def milestone_released(q, m):
    if not milestone_complete(q, m["id"]):
        return False
    return not m.get("hold") or (q.root / "acks" / m["id"]).exists()


def advance_milestones(q):
    ms = {m["id"]: m for m in q.cfg.get("milestones") or []}
    for m in ms.values():
        frags = [f for f in q.all() if f.front.get("milestone") == m["id"]]
        kinds = {f.front["kind"] for f in frags}
        if "decompose" not in kinds:
            if all(a in ms and milestone_released(q, ms[a]) for a in m.get("after") or []):
                q.create({
                    "title": f"Decompose {m['id']}",
                    "kind": "decompose",
                    "tier": "judgement",
                    "milestone": m["id"],
                }, f"## Goal\nCut {m['id']} into session-sized fragments.\n"
                   f"## Read first\n{m.get('source', '')}\n")
        elif "brief" not in kinds and milestone_complete(q, m["id"]):
            q.create({
                "title": f"Brief for {m['id']}",
                "kind": "brief",
                "tier": "judgement",
                "milestone": m["id"],
            }, f"## Goal\nBrief the operator on {m['id']}.\n")


def integrate(q, target):
    cfg = q.cfg
    iw = cfg["integration_worktree"]
    base = cfg["base"]
    branch = target.front["branch"]
    for _ in range(3):
        old = git(iw, "rev-parse", base).stdout.strip()
        git(iw, "checkout", "-q", branch)
        if git(iw, "rebase", "-q", base, check=False).returncode != 0:
            git(iw, "rebase", "--abort", check=False)
            git(iw, "checkout", "-q", "--detach")
            q.create({
                "title": f"Resolve conflict of {target.id}: {target.front.get('title', '')}",
                "kind": "conflict",
                "tier": "standard",
                "milestone": target.front.get("milestone"),
                "target": target.id,
                "branch": branch,
            }, f"## Goal\nMake {target.id} apply on {base} again.\n")
            target.note(f"rebase onto {base} conflicted; conflict fragment created")
            target.save()
            return
        failure = run_gate(cfg, iw)
        new = git(iw, "rev-parse", "HEAD").stdout.strip()
        git(iw, "checkout", "-q", "--detach")
        if failure:
            send_back(q, target, f"gate failed after rebase onto {base}:\n{failure}", why="gate-failed")
            return
        if git(iw, "update-ref", f"refs/heads/{base}", new, old, check=False).returncode == 0:
            target.note(f"integrated into {base} at {new[:12]}")
            q.move(target, "done", "integrated", detail=new[:12])
            return
    send_back(q, target, f"{base} kept moving during integration", max_attempts=1, why="base-moved")


# commands ---------------------------------------------------------------

def cmd_add(q, args):
    with q.locked():
        src = Fragment.read(args.file)
        frag = q.create(src.front, src.body)
    print(frag.id)
    return 0


AGENT_PROMPT = "Read .loop/FRAGMENT.md in this worktree and follow it exactly."


def base_checkouts(cfg):
    """Paths of worktrees that have the base branch checked out."""
    listing = git(cfg["integration_worktree"], "worktree", "list", "--porcelain").stdout
    paths, current = [], None
    for line in listing.splitlines():
        if line.startswith("worktree "):
            current = line[len("worktree "):]
        elif line == f"branch refs/heads/{cfg['base']}":
            paths.append(current)
    return paths


def record_tick(q, agent, rc, reason=""):
    (q.root / "ticks" / f"{agent}.json").write_text(json.dumps(
        {"ts": now().isoformat(), "rc": rc, "reason": reason}))


def last_tick(q, agent):
    path = q.root / "ticks" / f"{agent}.json"
    return json.loads(path.read_text()) if path.exists() else None


def cmd_tick(q, args):
    agent = args.agent
    if agent not in q.cfg["agents"]:
        raise SystemExit(f"loopq: unknown agent {agent!r}")
    q.actor = agent
    held = base_checkouts(q.cfg)
    if held:
        reason = (f"{q.cfg['base']} is checked out in {', '.join(held)}; "
                  "loopq moves it only while no worktree has it checked out")
        print(f"loopq: {reason}", file=sys.stderr)
        record_tick(q, agent, 2, reason)
        return 2
    rc = tick(q, agent)
    record_tick(q, agent, rc, "took work" if rc == 0 else "")
    if args.manual:
        if rc == 0:
            print(f"worktree: {q.cfg['agents'][agent]['worktree']}\nprompt: {AGENT_PROMPT}")
        else:
            print(f"nothing for {agent} now")
    return rc


def tick(q, agent):
    with q.locked():
        if collect(q, agent) == "busy":
            return 1
        expire_others(q, agent)
        advance_milestones(q)
        promote_humans(q)
        if (q.root / "paused").exists() or in_cooldown(q, agent):
            return 1
        frag = pick(q, agent)
        if frag is None:
            return 1
        frag.front["claimed_by"] = agent
        lease = parse_duration(q.cfg.get("lease", "4h"))
        frag.front["lease_until"] = (now() + lease).isoformat()
        if not prepare(q, agent, frag):
            frag.front["claimed_by"] = None
            frag.front["lease_until"] = None
            frag.save()
            print(f"loopq: worktree of {agent} is not clean", file=sys.stderr)
            return 1
        q.move(frag, "claimed", "claimed", agent)
    return 0


def cmd_cooldown(q, args):
    path = q.root / "cooldown" / args.agent
    with q.locked():
        if args.clear:
            path.unlink(missing_ok=True)
        elif args.until:
            path.write_text(dt.datetime.fromisoformat(args.until).isoformat())
        else:
            print(path.read_text().strip() if path.exists() else "none")
    return 0


def cmd_resolve(q, args):
    with q.locked():
        frag = q.get(args.id)
        if frag is None or frag.state != "human":
            print(f"loopq: {args.id} is not waiting on a human", file=sys.stderr)
            return 2
        frag.note(f"operator: {args.note}" if args.note else "operator resolved")
        release(frag)
        frag.front["notified"] = True
        if args.done:
            q.move(frag, "done", "resolved")
        elif frag.front.get("kind") == "human":
            frag.save()  # an operator step stays with the operator
            q.event("noted", frag.id, to="human", detail=args.note)
        else:
            q.move(frag, "ready", "requeued")
    return 0


def cmd_ack(q, args):
    with q.locked():
        (q.root / "acks" / args.milestone).write_text(now().isoformat())
    return 0


# rendering --------------------------------------------------------------

STATE_STYLE = {"ready": "cyan", "claimed": "yellow", "review": "magenta",
               "human": "bold red", "done": "green", "missing": "dim red"}
KIND_STYLE = {"work": "blue", "review": "magenta", "conflict": "red", "decompose": "cyan",
              "brief": "green", "human": "bold red"}
TIER_STYLE = {"judgement": "bold magenta", "standard": "blue", "mechanical": "bright_black"}
GOOD_EVENTS = {"integrated", "resolved", "resolved-conflict", "gate-passed", "reviewed",
               "decomposed", "briefed", "created"}
FAILED_ENDS = {"blocked", "expired", "gate-failed", "gave-up", "error", "changes-asked",
               "invalid-output", "review-unfinished", "base-moved"}

_console = None


def console():
    """Colour on a terminal; plain text, wide enough not to wrap, when piped."""
    global _console
    if _console is None:
        tty = sys.stdout.isatty()
        _console = Console(highlight=False, emoji=False,
                           width=None if tty or os.environ.get("COLUMNS") else 220)
    return _console


def ago(ts):
    if not ts:
        return ""
    delta = (now() - dt.datetime.fromisoformat(ts)).total_seconds()
    future, secs = delta < 0, abs(delta)
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if secs >= size:
            amount = f"{int(secs // size)}{unit}"
            break
    else:
        amount = f"{int(secs)}s"
    return f"in {amount}" if future else f"{amount} ago"


def span(start, end):
    if not end:
        return ""
    secs = (dt.datetime.fromisoformat(end) - dt.datetime.fromisoformat(start)).total_seconds()
    return f"{int(secs // 3600)}h{int(secs % 3600 // 60):02d}m" if secs >= 3600 else f"{int(secs // 60)}m{int(secs % 60):02d}s"


def styled(value, table):
    return Text(str(value), style=table.get(str(value), ""))


def event_style(event):
    if event in FAILED_ENDS:
        return "red"
    if event in GOOD_EVENTS:
        return "green"
    if event in ("claimed", "launched", "exited"):
        return "yellow"
    return "cyan"


def counts_text(q):
    text = Text()
    for i, s in enumerate(STATES):
        if i:
            text.append("  ")
        n = len(list((q.root / s).glob("*.md")))
        text.append("● ", style=STATE_STYLE[s] if n else "bright_black")
        text.append(f"{s} ")
        text.append(str(n), style=f"bold {STATE_STYLE[s]}" if n else "bright_black")
    return text


def grid():
    t = Table.grid(padding=(0, 2))
    t.add_column(style="bright_black", no_wrap=True)
    t.add_column()
    return t


def plain_table(*columns):
    t = Table(box=box.SIMPLE_HEAD, header_style="bold", pad_edge=False, show_edge=False)
    for col in columns:
        if isinstance(col, tuple):
            t.add_column(col[0], **col[1])
        else:
            t.add_column(col)
    return t


def command(label, cmd):
    line = Text("    ")
    line.append(f"{label:<9}", style="bright_black")
    line.append(cmd, style="cyan")
    console().print(line, soft_wrap=True)


# operator views --------------------------------------------------------

def lease_expired(frag):
    lease = frag.front.get("lease_until")
    return bool(lease) and dt.datetime.fromisoformat(lease) <= now()


def dep_states(q, frag):
    out = []
    for d in frag.front.get("deps") or []:
        other = q.get(d)
        out.append((d, other.state if other else "missing"))
    return out


def last_note(frag):
    if "## Notes" not in frag.body:
        return ""
    notes = frag.body.split("## Notes", 1)[1].strip().split("\n- ")
    return notes[-1].lstrip("- ").strip() if notes and notes[-1] else ""


def cmd_status(q, args):
    c = console()
    c.print(counts_text(q))
    claims = q.all("claimed")
    if claims:
        t = plain_table("Claimed", "Agent", "Lease", "Title")
        for f in claims:
            lease = f.front["lease_until"]
            t.add_row(Text(f.id, style="bold"), f.front["claimed_by"],
                      Text(f"{lease} ({ago(lease)})", style="red" if lease_expired(f) else ""),
                      Text(f.front.get("title", "")))
        c.print(t)
    done = q.done_ids()
    for f in q.all("human"):
        pending = [d for d in f.front.get("deps") or [] if d not in done]
        if pending:
            c.print(Text.assemble(("⏳ ", "yellow"), (f.id, "bold"),
                                  f" waiting on {', '.join(pending)}: ", f.front.get("title", "")))
        else:
            c.print(Text.assemble(("▶ ", "bold red"), (f.id, "bold"), " human: ",
                                  f.front.get("title", "")))
    for p in sorted((q.root / "cooldown").iterdir()):
        until = dt.datetime.fromisoformat(p.read_text().strip())
        if until > now():
            c.print(Text.assemble(("⏸ ", "yellow"), f"cooldown {p.name} until ",
                                  (until.isoformat(), "yellow"), f" ({ago(until.isoformat())})"))
    for p in sorted((q.root / "briefs").glob("*.md")):
        if not (q.root / "acks" / p.stem).exists():
            c.print(Text.assemble(("✉ ", "green"), f"brief {p.stem} unread: {p}"))
    return 0


def cmd_doctor(q, args):
    """Everything that needs attention, blockers first. Exit 1 when any."""
    cfg, problems = q.cfg, []  # (level, text)
    held = base_checkouts(cfg)
    if held:
        refused = [(n, last_tick(q, n)) for n in cfg["agents"]]
        refused = ", ".join(f"{n} {ago(r['ts'])}" for n, r in refused if r and r["rc"] == 2)
        problems.append(("blocker", f"{cfg['base']} is checked out in {', '.join(held)}: "
                                    "every tick is refused until you switch that worktree away"
                                    + (f" (last refused: {refused})" if refused else "")))
    if (q.root / "paused").exists():
        problems.append(("warn", "paused: agents collect but take nothing (loopq resume)"))
    claimed_by = {f.front.get("claimed_by"): f for f in q.all("claimed")}
    for frag in q.all("claimed"):
        if lease_expired(frag):
            agent = frag.front["claimed_by"]
            waiting = read_result(cfg["agents"][agent]["worktree"]) is not None
            problems.append(("warn", f"{frag.id} claimed by {agent}: lease expired "
                                     f"{ago(frag.front['lease_until'])} "
                                     f"({'result waiting' if waiting else 'no result'}); "
                                     "next tick collects it"))
    for name, spec in cfg["agents"].items():
        wt = Path(spec["worktree"])
        if not wt.exists():
            problems.append(("blocker", f"agent {name}: worktree {wt} is missing"))
            continue
        if name not in claimed_by and git(wt, "status", "--porcelain", check=False).stdout.strip():
            problems.append(("warn", f"agent {name}: worktree {wt} is dirty without a claim; "
                                     "ticks will skip it"))
        if in_cooldown(q, name):
            until = (q.root / "cooldown" / name).read_text().strip()
            problems.append(("info", f"agent {name}: cooling down until {until} ({ago(until)})"))
    done = q.done_ids()
    actionable = [f for f in q.all("human") if all(d in done for d in f.front.get("deps") or [])]
    if actionable:
        problems.append(("you", f"{len(actionable)} item(s) need you: loopq todo"))
    unread = [p.stem for p in sorted((q.root / "briefs").glob("*.md"))
              if not (q.root / "acks" / p.stem).exists()]
    if unread:
        problems.append(("you", f"unread brief(s): {', '.join(unread)} (loopq todo)"))
    c = console()
    c.print(Rule(Text(f"loopq · {cfg['project']}", style="bold"), align="left"))
    c.print(counts_text(q))
    if not problems:
        c.print(Text("✔ ok, nothing needs you", style="bold green"))
        return 0
    marks = {"blocker": ("✖ BLOCKER ", "bold red"), "warn": ("⚠ ", "yellow"),
             "info": ("ℹ ", "cyan"), "you": ("▶ ", "bold magenta")}
    order = ["blocker", "warn", "you", "info"]
    for level, text in sorted(problems, key=lambda p: order.index(p[0])):
        mark, style = marks[level]
        line = Text(mark, style=style)
        line.append(text, style="red" if level == "blocker" else "")
        c.print(line)
    return 1


def cmd_todo(q, args):
    c = console()
    now_items, waiting = [], []
    for frag in q.all("human"):
        pending = [(d, st) for d, st in dep_states(q, frag) if st != "done"]
        (waiting if pending else now_items).append((frag, pending))
    c.print(Rule(Text("Do now", style="bold red"), align="left"))
    for frag, _ in now_items:
        head = Text("▶ ", style="bold red")
        head.append(frag.id, style="bold")
        head.append("  ")
        head.append(frag.front.get("title", ""), style="bold")
        head.append(f"  {frag.front.get('kind')}", style=KIND_STYLE.get(frag.front.get("kind"), ""))
        c.print(head)
        note = last_note(frag)
        if note:
            c.print(Text(f"    {note.splitlines()[0][:160]}", style="italic bright_black"))
        command("read", f"cat {frag.path}")
        command("finish", f'loopq resolve {frag.id} --done --note "..."')
        if frag.front.get("kind") != "human":
            command("or", f'loopq retry {frag.id} --note "..."')
    if not now_items:
        c.print(Text("  nothing", style="bright_black"))
    c.print(Rule(Text("Waiting on the loop", style="bold yellow"), align="left"))
    for frag, pending in waiting:
        line = Text("⏳ ")
        line.append(frag.id, style="bold")
        line.append(f"  {frag.front.get('title', '')}  ")
        line.append("waiting on ", style="bright_black")
        for i, (d, st) in enumerate(pending):
            if i:
                line.append(", ")
            line.append(d)
            line.append(f" ({st})", style=STATE_STYLE.get(st, ""))
        c.print(line)
    if not waiting:
        c.print(Text("  nothing", style="bright_black"))
    c.print(Rule(Text("Briefs to read", style="bold green"), align="left"))
    unread = [p for p in sorted((q.root / "briefs").glob("*.md"))
              if not (q.root / "acks" / p.stem).exists()]
    for p in unread:
        c.print(Text.assemble(("✉ ", "green"), (p.stem, "bold")))
        command("read", f"cat {p}")
        command("then", f"loopq ack {p.stem}")
    if not unread:
        c.print(Text("  nothing", style="bright_black"))
    return 0


def sessions(q, fid=None, agent=None):
    """One entry per claim, built from the event log: who, when, how it ended."""
    events = q.events()
    out = []
    for i, e in enumerate(events):
        if e["event"] != "claimed" or (fid and e["id"] != fid) or (agent and e["agent"] != agent):
            continue
        s = {"id": e["id"], "agent": e["agent"], "start": e["ts"], "end": None,
             "outcome": "running", "exit": None, "log": None}
        for later in events[i + 1:]:
            if later["id"] != e["id"]:
                continue
            if later["event"] == "launched":
                s["log"] = later["detail"]
            elif later["event"] == "exited":
                s["exit"] = int(later["detail"])
            elif later["event"] != "claimed":
                s["end"], s["outcome"] = later["ts"], later["event"]
                break
            else:
                break
        out.append(s)
    return out


def session_failed(s):
    return (s["exit"] not in (None, 0)) or s["outcome"] in FAILED_ENDS


def cmd_runs(q, args):
    rows = sessions(q, agent=args.agent)
    if args.failed:
        rows = [s for s in rows if session_failed(s)]
    t = plain_table("Started", "Agent", "Fragment", "Outcome", "Exit", "Took", "Title")
    for s in rows[-args.limit:]:
        frag = q.get(s["id"])
        exit_cell = Text("")
        if s["exit"] is not None:
            exit_cell = Text(f"exit {s['exit']}", style="green" if s["exit"] == 0 else "bold red")
        outcome = Text(s["outcome"], style="yellow" if s["outcome"] == "running" else event_style(s["outcome"]))
        t.add_row(Text(f"{s['start']} ({ago(s['start'])})"), s["agent"], Text(s["id"], style="bold"),
                  outcome, exit_cell, span(s["start"], s["end"]),
                  Text(frag.front.get("title", "") if frag else ""))
    console().print(t if rows else Text("no sessions recorded", style="bright_black"))
    return 0


def transcript_files(q, s):
    pattern = q.cfg["agents"].get(s["agent"], {}).get("transcripts")
    if not pattern:
        return []
    start = dt.datetime.fromisoformat(s["start"]).timestamp()
    end = dt.datetime.fromisoformat(s["end"]).timestamp() if s["end"] else float("inf")
    files = [Path(p) for p in glob.glob(os.path.expanduser(pattern), recursive=True)]
    return sorted(p for p in files if start <= p.stat().st_mtime <= end + 60)


def cmd_session(q, args):
    found = sessions(q, fid=args.id)
    if not found:
        print(f"loopq: no session recorded for {args.id}", file=sys.stderr)
        return 1
    c = console()
    for s in found:
        title = Text.assemble((s["id"], "bold"), " by ", (s["agent"], "bold"), "  ",
                              (s["outcome"], event_style(s["outcome"])),
                              f"  {s['start']} → {s['end'] or 'now'}")
        c.print(Rule(title, align="left"))
        paths = [Path(s["log"])] if s["log"] else transcript_files(q, s)
        if not paths:
            c.print(Text("(no captured output: launch with `loopq run`, or set the agent's "
                         "`transcripts` glob)", style="bright_black"))
        for path in paths:
            c.print(Text(f"--- {path}", style="bright_black"), soft_wrap=True)
            if not args.paths:
                c.out(path.read_text(errors="replace"), end="", highlight=False)
    return 0


def history_table(q, fid):
    t = plain_table("When", "Event", "To", "By", "Detail")
    for e in q.events():
        if e["id"] == fid:
            t.add_row(Text(f"{e['ts']} ({ago(e['ts'])})"), Text(e["event"], style=event_style(e["event"])),
                      styled(e["to"] or "", STATE_STYLE), e["agent"] or "", Text(e["detail"] or ""))
    return t


def cmd_history(q, args):
    console().print(history_table(q, args.id))
    return 0


def cmd_show(q, args):
    frag = q.get(args.id)
    if frag is None:
        print(f"loopq: no fragment {args.id}", file=sys.stderr)
        return 2
    c, f = console(), frag.front
    info = grid()
    info.add_row("state", styled(frag.state, STATE_STYLE))
    info.add_row("kind", styled(f.get("kind", ""), KIND_STYLE))
    info.add_row("tier", styled(f.get("tier", ""), TIER_STYLE))
    for key in ("milestone", "branch", "target", "author", "attempts", "claimed_by", "lease_until"):
        if f.get(key) not in (None, "", 0):
            info.add_row(key, Text(str(f[key])))
    info.add_row("file", Text(str(frag.path), style="bright_black"))
    for d, st in dep_states(q, frag):
        info.add_row("dep", Text.assemble((d, "bold"), "  ", (st, STATE_STYLE.get(st, ""))))
    iw, base = q.cfg["integration_worktree"], q.cfg["base"]
    merged = git(iw, "log", base, f"--grep=Loop-Fragment: {frag.id}", "--format=%h %s", check=False).stdout
    for line in merged.splitlines():
        info.add_row(f"in {base}", Text(line, style="green"))
    branch = f.get("branch")
    if branch and frag.state != "done" and branch_exists(iw, branch):
        pending = git(iw, "log", f"{base}..{branch}", "--format=%h %s", check=False).stdout
        for line in pending.splitlines():
            info.add_row("pending", Text(line, style="yellow"))
    c.print(Panel(info, title=Text(f"{frag.id} · {f.get('title', '')}", style="bold"),
                  title_align="left", border_style=STATE_STYLE.get(frag.state, "")))
    c.print(Markdown(frag.body))
    c.print(Rule(Text("history", style="bold"), align="left"))
    c.print(history_table(q, frag.id))
    return 0


def why_not(q, agent, frag, done):
    spec = q.cfg["agents"][agent]
    f = frag.front
    reasons = []
    if f.get("kind") not in spec.get("kinds", []):
        reasons.append(f"kind {f.get('kind')}")
    if f.get("tier") not in spec.get("tiers", []):
        reasons.append(f"tier {f.get('tier')}")
    missing = [d for d in f.get("deps") or [] if d not in done]
    if missing:
        reasons.append("deps " + ", ".join(missing))
    if f.get("kind") == "review" and f.get("author") == agent:
        reasons.append("own work")
    return reasons


def cmd_why(q, args):
    agent = args.agent
    if agent not in q.cfg["agents"]:
        raise SystemExit(f"loopq: unknown agent {agent!r}")
    c = console()
    for f in q.all("claimed"):
        if f.front.get("claimed_by") == agent:
            state = f"lease expired {ago(f.front['lease_until'])}" if lease_expired(f) \
                else f"lease ends {ago(f.front['lease_until'])}"
            c.print(Text.assemble(("● busy ", "yellow"), f"holds ", (f.id, "bold"), f" ({state})"))
    held = base_checkouts(q.cfg)
    if held:
        c.print(Text(f"✖ refused: {q.cfg['base']} is checked out in {', '.join(held)}", style="bold red"))
    if (q.root / "paused").exists():
        c.print(Text("⏸ paused", style="yellow"))
    if in_cooldown(q, agent):
        until = (q.root / "cooldown" / agent).read_text().strip()
        c.print(Text(f"⏸ cooldown until {until} ({ago(until)})", style="yellow"))
    done = q.done_ids()
    ready = q.all("ready")
    if not ready:
        c.print(Text("no ready fragments", style="bright_black"))
        return 0
    t = plain_table("Ready", "Kind", "Tier", "Title", "For " + agent)
    for frag in ready:
        reasons = why_not(q, agent, frag, done)
        verdict = Text("✔ eligible", style="bold green") if not reasons \
            else Text("not for it: " + "; ".join(reasons), style="red")
        t.add_row(Text(frag.id, style="bold"), styled(frag.front.get("kind", ""), KIND_STYLE),
                  styled(frag.front.get("tier", ""), TIER_STYLE), Text(frag.front.get("title", "")), verdict)
    c.print(t)
    return 0


def progress_bar(done, total, width=12):
    if not total:
        return Text("─" * width, style="bright_black")
    filled = round(width * done / total)
    return Text.assemble(("█" * filled, "green"), ("░" * (width - filled), "bright_black"),
                         f" {done}/{total}")


def cmd_milestones(q, args):
    ms = {m["id"]: m for m in q.cfg.get("milestones") or []}
    t = plain_table("Milestone", "Status", "Progress", "States")
    for m in ms.values():
        frags = [f for f in q.all() if f.front.get("milestone") == m["id"]]
        counts = {}
        for f in frags:
            counts[f.state] = counts.get(f.state, 0) + 1
        if milestone_complete(q, m["id"]):
            status = Text("complete", style="bold green")
            if m.get("hold") and not (q.root / "acks" / m["id"]).exists():
                status.append(", held until loopq ack " + m["id"], style="yellow")
        elif not frags:
            waiting = [a for a in m.get("after") or [] if not (a in ms and milestone_released(q, ms[a]))]
            names = ", ".join(waiting) if len(waiting) <= 3 else f"{len(waiting)} milestones"
            status = Text("waiting on " + names, style="bright_black") if waiting \
                else Text("starts at the next tick", style="cyan")
        else:
            status = Text("in progress", style="yellow")
        states = Text()
        for s in STATES:
            if s in counts:
                if states:
                    states.append("  ")
                states.append(f"{s} {counts[s]}", style=STATE_STYLE[s])
        t.add_row(Text(m["id"], style="bold"), status, progress_bar(counts.get("done", 0), len(frags)), states)
    console().print(t)
    return 0


# operator actions -------------------------------------------------------

def cmd_release(q, args):
    with q.locked():
        frag = q.get(args.id)
        if frag is None or frag.state != "claimed":
            print(f"loopq: {args.id} is not claimed", file=sys.stderr)
            return 2
        agent = frag.front["claimed_by"]
        if read_result(q.cfg["agents"][agent]["worktree"]) is not None:
            collect(q, agent)
            return 0
        try:
            expire(q, frag)
        except GitError as err:
            to_human_on_error(q, agent, [frag.id], err)
            return 1
        q.event("released", frag.id, detail=args.note)
    return 0


def cmd_retry(q, args):
    with q.locked():
        frag = q.get(args.id)
        if frag is None or frag.state in ("done", "claimed"):
            print(f"loopq: {args.id} cannot be retried from its state", file=sys.stderr)
            return 2
        if frag.front.get("kind") == "human":
            print(f"loopq: {args.id} is an operator step; close it with "
                  f"`loopq resolve {args.id} --done`", file=sys.stderr)
            return 2
        frag.front["attempts"] = 0
        if args.tier:
            frag.note(f"operator: tier {frag.front.get('tier')} -> {args.tier}")
            frag.front["tier"] = args.tier
        frag.note(f"operator retry: {args.note}" if args.note else "operator retry")
        release(frag)
        q.move(frag, "ready", "retried")
    return 0


def cmd_pause(q, args):
    (q.root / "paused").write_text(now().isoformat())
    return 0


def cmd_resume(q, args):
    (q.root / "paused").unlink(missing_ok=True)
    return 0


# launcher ---------------------------------------------------------------

def pid_alive(path):
    try:
        os.kill(int(path.read_text().strip()), 0)
        return True
    except (FileNotFoundError, ValueError, ProcessLookupError):
        return False
    except PermissionError:
        return True


def agent_argv(spec, **values):
    cmd = spec.get("command")
    if not cmd:
        raise SystemExit("loopq: this agent has no `command` in the config")
    parts = shlex.split(cmd) if isinstance(cmd, str) else list(cmd)
    return [str(p).format(**values) for p in parts]


def cmd_run(q, args):
    """Tick, launch the agent on what it got, capture its output, collect."""
    agent = args.agent
    spec = q.cfg["agents"].get(agent)
    if spec is None:
        raise SystemExit(f"loopq: unknown agent {agent!r}")
    pidfile = q.root / "logs" / f"{agent}.pid"
    if pid_alive(pidfile):
        return 1
    rc = cmd_tick(q, argparse.Namespace(agent=agent, manual=False))
    if rc != 0:
        return rc
    frag = next(f for f in q.all("claimed") if f.front.get("claimed_by") == agent)
    runs = q.root / "logs" / "runs"
    runs.mkdir(exist_ok=True)
    stamp = now().strftime("%Y%m%dT%H%M%S")
    log = runs / f"{frag.id}-{agent}-{stamp}.log"
    argv = agent_argv(spec, prompt=AGENT_PROMPT, worktree=spec["worktree"], id=frag.id)
    q.event("launched", frag.id, agent, "claimed", str(log))
    timeout = parse_duration(q.cfg.get("lease", "4h")).total_seconds()
    with open(log, "w") as out:
        proc = subprocess.Popen(argv, cwd=spec["worktree"], stdout=out, stderr=subprocess.STDOUT,
                                env={**os.environ, "LOOPQ_FRAGMENT": frag.id, "LOOPQ_AGENT": agent})
        pidfile.write_text(str(proc.pid))
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            code = proc.wait()
            out.write("\nloopq: killed at the end of the lease\n")
    pidfile.unlink(missing_ok=True)
    q.event("exited", frag.id, agent, "claimed", str(code))
    with q.locked():
        q.actor = agent
        wt = spec["worktree"]
        if code != 0 and read_result(wt) is None:
            current = q.get(frag.id)
            if current is not None and current.state == "claimed":
                current.note(f"{agent} exited {code} without a result; see {log}")
                current.save()
                safe_expire(q, current)
                start_cooldown(q, agent)
        else:
            collect(q, agent)
    return code


def main(argv=None):
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default=os.environ.get("LOOPQ_CONFIG"))
    parser = argparse.ArgumentParser(prog="loopq", parents=[common])
    sub = parser.add_subparsers(dest="command")
    tick = sub.add_parser("tick", parents=[common])
    tick.add_argument("--agent", required=True)
    tick.add_argument("--manual", action="store_true")
    add = sub.add_parser("add", parents=[common])
    add.add_argument("file")
    cool = sub.add_parser("cooldown", parents=[common])
    cool.add_argument("--agent", required=True)
    cool.add_argument("--until")
    cool.add_argument("--clear", action="store_true")
    res = sub.add_parser("resolve", parents=[common])
    res.add_argument("id")
    res.add_argument("--note", default="")
    mode = res.add_mutually_exclusive_group(required=True)
    mode.add_argument("--done", action="store_true")
    mode.add_argument("--requeue", action="store_true")
    sub.add_parser("status", parents=[common])
    ack = sub.add_parser("ack", parents=[common])
    ack.add_argument("milestone")
    sub.add_parser("doctor", parents=[common], help="what needs attention; exit 1 if anything")
    sub.add_parser("todo", parents=[common], help="your inbox: human steps and briefs")
    sub.add_parser("milestones", parents=[common])
    for name in ("show", "history"):
        sub.add_parser(name, parents=[common]).add_argument("id")
    why = sub.add_parser("why", parents=[common], help="why an agent takes nothing")
    why.add_argument("agent")
    runs = sub.add_parser("runs", parents=[common], help="agent sessions, from any launcher")
    runs.add_argument("--agent")
    runs.add_argument("--failed", action="store_true")
    runs.add_argument("--limit", type=int, default=30)
    sess = sub.add_parser("session", parents=[common], help="full output of a fragment's sessions")
    sess.add_argument("id")
    sess.add_argument("--paths", action="store_true", help="print file paths only")
    for name in ("release", "retry"):
        p = sub.add_parser(name, parents=[common])
        p.add_argument("id")
        p.add_argument("--note", default="")
        if name == "retry":
            p.add_argument("--tier", choices=("judgement", "standard", "mechanical"),
                           help="move the fragment to another tier")
    sub.add_parser("pause", parents=[common])
    sub.add_parser("resume", parents=[common])
    run = sub.add_parser("run", parents=[common], help="tick, launch the agent's command, collect")
    run.add_argument("--agent", required=True)
    args = parser.parse_args(argv)
    if not args.config:
        parser.error("--config or LOOPQ_CONFIG is required")
    cfg = yaml.safe_load(Path(args.config).read_text())
    q = Queue(cfg)
    commands = {"tick": cmd_tick, "add": cmd_add, "cooldown": cmd_cooldown,
                "resolve": cmd_resolve, "ack": cmd_ack, "status": cmd_status,
                "doctor": cmd_doctor, "todo": cmd_todo, "milestones": cmd_milestones,
                "show": cmd_show, "history": cmd_history, "why": cmd_why,
                "runs": cmd_runs, "session": cmd_session, "release": cmd_release,
                "retry": cmd_retry, "pause": cmd_pause, "resume": cmd_resume,
                "run": cmd_run}
    return commands[args.command or "doctor"](q, args)


if __name__ == "__main__":
    sys.exit(main())
