#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml==6.0.3"]
# ///
"""loopq: a local fragment queue that lets several agent budgets pull
session-sized work, with gates, cross-agent review and integration done by
this script. See the fragment loop spec for the contract."""

import argparse
import datetime as dt
import fcntl
import os
import re
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

import yaml

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
        "findings."
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
        for d in (*STATES, "briefs", "logs", "cooldown", "acks"):
            (self.root / d).mkdir(parents=True, exist_ok=True)

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

    def move(self, frag, state):
        dest = self.root / state / frag.path.name
        frag.save()
        os.rename(frag.path, dest)
        frag.path = dest

    def next_id(self):
        counter = self.root / "next_id"
        n = int(counter.read_text()) if counter.exists() else 1
        counter.write_text(str(n + 1))
        return f"{self.cfg['prefix']}-{n:04d}"

    def create(self, front, body, state="ready"):
        front = dict(front)
        front["id"] = self.next_id()
        front.setdefault("deps", [])
        front.setdefault("attempts", 0)
        front.setdefault("claimed_by", None)
        front.setdefault("lease_until", None)
        ordered = {"id": front.pop("id"), **front}
        frag = Fragment(self.root / state / f"{ordered['id']}.md", ordered, body)
        frag.save()
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
    res = Fragment.read(path)
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
        q.move(frag, "human")
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
    q.move(frag, "ready")


def safe_expire(q, frag):
    agent = frag.front["claimed_by"]
    try:
        expire(q, frag)
    except GitError as err:
        to_human_on_error(q, agent, [frag.id], err)


def expire_others(q, agent):
    for frag in q.all("claimed"):
        if frag.front.get("claimed_by") == agent:
            continue
        if dt.datetime.fromisoformat(frag.front["lease_until"]) <= now():
            safe_expire(q, frag)


def collect_work(q, agent, wt, frag, front, body):
    status = front.get("status")
    message = front.get("commit") or f"wip({frag.id}): {frag.front.get('title', '')}"
    commit_all(wt, message, frag.id, agent)
    frag.front["last_agent"] = agent
    if status == "done":
        failure = run_gate(q.cfg, wt)
        if failure is None:
            q.move(frag, "review")
            q.create({
                "title": f"Review {frag.id}: {frag.front.get('title', '')}",
                "kind": "review",
                "tier": frag.front.get("tier"),
                "milestone": frag.front.get("milestone"),
                "target": frag.id,
                "author": agent,
                "branch": frag.front["branch"],
            }, f"## Goal\nReview {frag.id}.\n")
            return
        send_back(q, frag, failure)
    elif status == "blocked":
        frag.note(f"blocked ({agent}):\n{body.strip()}")
        q.move(frag, "human")
        notify(q.cfg, f"{frag.id} is blocked: {frag.front.get('title', '')}")
    else:  # parked
        frag.note(f"parked by {agent}:\n{body.strip()}")
        q.move(frag, "ready")
        start_cooldown(q, agent)


def notify(cfg, message):
    cmd = cfg.get("notify")
    if cmd is None:
        safe = message.replace('"', "'")
        cmd = ["osascript", "-e", f'display notification "{safe}" with title "loopq"']
        subprocess.run(cmd, capture_output=True)
        return
    subprocess.run([*cmd, message], capture_output=True)


def send_back(q, frag, reason, max_attempts=3):
    frag.front["attempts"] = int(frag.front.get("attempts") or 0) + 1
    frag.note(reason)
    release(frag)
    if frag.front["attempts"] >= max_attempts:
        q.move(frag, "human")
        notify(q.cfg, f"{frag.id} needs you after {frag.front['attempts']} attempts")
    else:
        q.move(frag, "ready")


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
    q.move(frag, "done")
    if front.get("status") != "done":
        send_back(q, target, f"review by {agent} did not finish: {body.strip()}")
        return
    if front.get("verdict") == "approve":
        integrate(q, target)
    else:
        send_back(q, target, f"review by {agent} asked for changes:\n{body.strip()}")


def collect_conflict(q, agent, wt, frag, front, body):
    target = q.get(frag.front["target"])
    if front.get("status") != "done":
        discard(wt)
        frag.note(f"{front.get('status')} by {agent}:\n{body.strip()}")
        if front.get("status") == "parked":
            q.move(frag, "ready")
            start_cooldown(q, agent)
        else:
            q.move(frag, "human")
            notify(q.cfg, f"{frag.id} is blocked: {frag.front.get('title', '')}")
        return
    message = front.get("commit") or target.front.get("title", frag.id)
    commit_all(wt, message, target.id, agent)
    git(wt, "branch", "-f", frag.front["branch"], "HEAD")
    frag.note(f"resolved by {agent}")
    q.move(frag, "done")
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
        send_back(q, frag, f"{front.get('status')} by {agent}:\n{body.strip()}")
        return
    errors = validate_batch(q, outs)
    if errors:
        send_back(q, frag, "invalid decomposition:\n" + "\n".join(errors))
        return
    ids = {}
    for o in outs:
        ids[o.path.stem] = q.next_id()
    for o in outs:
        fr = {k: v for k, v in o.front.items() if k != "id"}
        fr["deps"] = [ids.get(d, d) for d in fr["deps"]]
        fr["milestone"] = fr.get("milestone") or frag.front.get("milestone")
        state = "human" if fr["kind"] == "human" else "ready"
        new = Fragment(q.root / state / f"{ids[o.path.stem]}.md",
                       {"id": ids[o.path.stem], "attempts": 0, "claimed_by": None,
                        "lease_until": None, **fr}, o.body)
        new.save()
        if state == "human":
            notify(q.cfg, f"{new.id} needs you: {fr['title']}")
    frag.note(f"decomposed by {agent} into {', '.join(ids.values())}")
    q.move(frag, "done")


def collect_brief(q, agent, wt, frag, front, body):
    discard(wt)
    if front.get("status") != "done":
        send_back(q, frag, f"{front.get('status')} by {agent}:\n{body.strip()}")
        return
    mid = frag.front.get("milestone")
    path = q.root / "briefs" / f"{mid}.md"
    path.write_text(body.strip() + "\n")
    q.move(frag, "done")
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
            send_back(q, target, f"gate failed after rebase onto {base}:\n{failure}")
            return
        if git(iw, "update-ref", f"refs/heads/{base}", new, old, check=False).returncode == 0:
            target.note(f"integrated into {base} at {new[:12]}")
            q.move(target, "done")
            return
    send_back(q, target, f"{base} kept moving during integration", max_attempts=1)


# commands ---------------------------------------------------------------

def cmd_add(q, args):
    with q.locked():
        src = Fragment.read(args.file)
        frag = q.create(src.front, src.body)
    print(frag.id)
    return 0


AGENT_PROMPT = "Read .loop/FRAGMENT.md in this worktree and follow it exactly."


def base_checked_out(cfg):
    listing = git(cfg["integration_worktree"], "worktree", "list", "--porcelain").stdout
    return f"branch refs/heads/{cfg['base']}" in listing.splitlines()


def cmd_tick(q, args):
    agent = args.agent
    if agent not in q.cfg["agents"]:
        raise SystemExit(f"loopq: unknown agent {agent!r}")
    if base_checked_out(q.cfg):
        print(f"loopq: {q.cfg['base']} is checked out in a worktree; "
              "loopq moves it only while no worktree has it checked out", file=sys.stderr)
        return 2
    rc = tick(q, agent)
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
        if in_cooldown(q, agent):
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
        q.move(frag, "claimed")
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


def cmd_status(q, args):
    counts = "  ".join(f"{s} {len(list((q.root / s).glob('*.md')))}" for s in STATES)
    print(counts)
    for f in q.all("claimed"):
        print(f"{f.id} claimed by {f.front['claimed_by']} until {f.front['lease_until']}: "
              f"{f.front.get('title', '')}")
    for f in q.all("human"):
        print(f"{f.id} human: {f.front.get('title', '')}")
    for p in sorted((q.root / "cooldown").iterdir()):
        until = dt.datetime.fromisoformat(p.read_text().strip())
        if until > now():
            print(f"cooldown {p.name} until {until.isoformat()}")
    for p in sorted((q.root / "briefs").glob("*.md")):
        if not (q.root / "acks" / p.stem).exists():
            print(f"brief {p.stem} unread: {p}")
    return 0


def cmd_resolve(q, args):
    with q.locked():
        frag = q.get(args.id)
        if frag is None or frag.state != "human":
            print(f"loopq: {args.id} is not waiting on a human", file=sys.stderr)
            return 2
        frag.note(f"operator: {args.note}" if args.note else "operator resolved")
        release(frag)
        q.move(frag, "done" if args.done else "ready")
    return 0


def cmd_ack(q, args):
    with q.locked():
        (q.root / "acks" / args.milestone).write_text(now().isoformat())
    return 0


def main(argv=None):
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default=os.environ.get("LOOPQ_CONFIG"))
    parser = argparse.ArgumentParser(prog="loopq", parents=[common])
    sub = parser.add_subparsers(dest="command", required=True)
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
    args = parser.parse_args(argv)
    if not args.config:
        parser.error("--config or LOOPQ_CONFIG is required")
    cfg = yaml.safe_load(Path(args.config).read_text())
    q = Queue(cfg)
    commands = {"tick": cmd_tick, "add": cmd_add, "cooldown": cmd_cooldown,
                "resolve": cmd_resolve, "ack": cmd_ack, "status": cmd_status}
    return commands[args.command](q, args)


if __name__ == "__main__":
    sys.exit(main())
