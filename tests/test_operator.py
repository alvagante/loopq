"""Operator commands: health, inbox, inspection, history, runs, sessions and
the provider-agnostic launcher."""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime

import yaml

from conftest import LOOPQ, git
from test_milestones import with_milestones, write_out

LATER = "2026-09-25T14:01:00+00:00"


# lease expiry must not destroy a finished result ----------------------------

def test_expired_claim_with_a_result_is_collected_not_discarded_by_another_agent(loop):
    fid = loop.add(title="slow finisher")
    loop.tick("a")
    (loop.wt("a") / "done.txt").write_text("done\n")
    loop.write_result("a", commit="feat: finish")

    loop.tick("b", now=LATER)

    assert loop.state_of(fid) == "review"
    assert "feat: finish" in git(loop.repo, "log", "-1", "--format=%s", "loop/tb-0001").stdout


# event log and history ------------------------------------------------------

def test_history_lists_every_transition_of_a_fragment(loop):
    fid = loop.add(title="one")
    loop.tick("a")
    loop.write_result("a", status="blocked", body="need a token")
    loop.tick("a")

    out = loop.run("history", fid).stdout

    lines = out.strip().splitlines()
    assert re.search(r"created\s+ready", lines[2])
    assert re.search(r"claimed\s+claimed\s+a", out)
    assert re.search(r"blocked\s+human", lines[-1])
    events = [json.loads(l) for l in (loop.queue / "logs" / "events.jsonl").read_text().splitlines()]
    assert {e["id"] for e in events} >= {fid}


# doctor ---------------------------------------------------------------------

def test_doctor_is_clean_on_a_healthy_loop(loop):
    res = loop.run("doctor")

    assert res.returncode == 0, res.stdout
    assert "ok" in res.stdout


def test_doctor_reports_base_checked_out_expired_leases_and_refused_ticks(loop):
    loop.add(title="one")
    loop.tick("a")
    git(loop.repo, "checkout", "-q", "tools")
    loop.tick("b")  # refused: base checked out

    res = loop.run("doctor", now=LATER)

    assert res.returncode == 1
    assert "tools is checked out" in res.stdout
    assert str(loop.repo) in res.stdout
    assert "tb-0001" in res.stdout and "expired" in res.stdout
    assert "refused" in res.stdout and "b" in res.stdout


def test_bare_loopq_runs_doctor(loop):
    res = loop.run()

    assert res.returncode == 0
    assert "ok" in res.stdout


# todo -----------------------------------------------------------------------

def test_todo_splits_actionable_and_waiting_human_items_and_unread_briefs(loop):
    work = loop.add(title="build")
    ready_h = loop.add(title="create token", kind="human")
    waiting_h = loop.add(title="verify on hardware", kind="human", deps=[work])
    assert loop.state_of(ready_h) == loop.state_of(waiting_h) == "human"
    (loop.queue / "briefs" / "m1.md").write_text("brief\n")

    out = loop.run("todo").stdout

    act, wait = out.index("Do now"), out.index("Waiting")
    assert act < out.index("create token") < wait < out.index("verify on hardware")
    assert f"loopq resolve {ready_h} --done" in out
    assert work in out.split("Waiting", 1)[1]
    assert "loopq ack m1" in out


def test_decomposed_human_step_notifies_only_once_its_deps_are_done(loop):
    with_milestones(loop)
    loop.tick("a")
    write_out(loop, "a", "build", title="build", kind="work", tier="standard", deps=[])
    write_out(loop, "a", "verify", title="verify on hardware", kind="human", tier="standard", deps=["build"])
    loop.write_result("a")
    loop.tick("a")

    assert not any("verify on hardware" in n for n in loop.notifications())

    [build] = [i for i in loop.ids_in("claimed")]
    (loop.queue / "claimed" / f"{build}.md").rename(loop.queue / "done" / f"{build}.md")
    loop.tick("b")

    assert sum("verify on hardware" in n for n in loop.notifications()) == 1
    loop.tick("b")
    assert sum("verify on hardware" in n for n in loop.notifications()) == 1


# show and why ---------------------------------------------------------------

def test_show_prints_fragment_dependencies_and_integrated_commits(loop):
    dep = loop.add(title="first")
    fid = loop.add(title="second", deps=[dep])
    loop.tick("a")
    (loop.wt("a") / "x.txt").write_text("x\n")
    loop.write_result("a", commit="feat: first")
    loop.tick("a")  # gate passes, review created
    loop.tick("b")  # b reviews
    loop.write_result("b", verdict="approve")
    loop.tick("b")

    out = loop.run("show", dep).stdout
    assert re.search(r"state\s+done", out) and "feat: first" in out

    out = loop.run("show", fid).stdout
    assert "second" in out and re.search(rf"{dep}\s+done", out)


def test_why_explains_what_keeps_an_agent_idle(loop):
    loop.config["agents"]["b"]["tiers"] = ["mechanical"]
    loop.save_config()
    blocker = loop.add(title="blocker", tier="mechanical")
    loop.add(title="needs judgement", tier="judgement")
    loop.add(title="after blocker", tier="mechanical", deps=[blocker])
    loop.tick("a")  # a takes the blocker

    out = loop.run("why", "b").stdout

    assert "needs judgement" in out and "tier judgement" in out
    assert "after blocker" in out and blocker in out


# milestones -----------------------------------------------------------------

def test_milestones_shows_progress_and_what_each_waits_on(loop):
    with_milestones(loop)
    loop.tick("a")

    out = loop.run("milestones").stdout

    m1 = next(l for l in out.splitlines() if l.startswith("m1"))
    m2 = next(l for l in out.splitlines() if l.startswith("m2"))
    assert "claimed 1" in m1
    assert "waiting on m1" in m2


# release, retry, pause ------------------------------------------------------

def test_release_returns_a_claim_without_cooling_the_agent(loop):
    fid = loop.add(title="stuck")
    loop.tick("a")

    assert loop.run("release", fid).returncode == 0

    assert loop.state_of(fid) == "ready"
    assert loop.tick("a").returncode == 0


def test_handoff_keeps_partial_work_cools_the_holder_and_waits_for_the_target(loop):
    fid = loop.add(title="hit limits")
    loop.tick("a")
    (loop.wt("a") / "partial.txt").write_text("half\n")

    res = loop.run("handoff", fid, "--to", "b", "--note", "a hit its usage limit")

    assert res.returncode == 0, res.stderr
    assert "loopq --loop demo run --agent b" in res.stdout
    front, body = loop.fragment(fid)
    assert loop.state_of(fid) == "ready" and front["assigned_to"] == "b"
    assert "handed off from a to b: a hit its usage limit" in body
    assert loop.tick("a").returncode == 1  # cooling down
    loop.run("cooldown", "--agent", "a", "--clear")
    assert loop.tick("a").returncode == 1  # waiting for b
    assert "handed to b" in loop.run("why", "a").stdout
    assert loop.tick("b").returncode == 0
    assert (loop.wt("b") / "partial.txt").read_text() == "half\n"
    assert "assigned_to" not in loop.fragment(fid)[0]


def test_handoff_without_target_lets_any_other_agent_take_it(loop):
    fid = loop.add(title="hit limits")
    loop.tick("a")

    assert loop.run("handoff", fid).returncode == 0

    assert loop.tick("a").returncode == 1
    assert loop.tick("b").returncode == 0


def test_handoff_refuses_the_holder_an_ineligible_agent_and_a_cooling_one(loop):
    fid = loop.add(title="judgement call", tier="judgement")
    loop.tick("a")
    loop.config["agents"]["b"]["tiers"] = ["mechanical"]
    loop.save_config()

    assert loop.run("handoff", fid, "--to", "a").returncode == 2
    assert "tier judgement" in loop.run("handoff", fid, "--to", "b").stderr
    loop.config["agents"]["b"]["tiers"] = ["judgement"]
    loop.save_config()
    loop.run("cooldown", "--agent", "b", "--until", "2099-01-01T00:00:00+00:00")
    assert "cooling down" in loop.run("handoff", fid, "--to", "b").stderr
    assert loop.state_of(fid) == "claimed"


def test_handoff_stops_a_stuck_run_and_keeps_its_work(loop):
    use_command(loop, "a", "echo partial > p.txt; exec sleep 60")
    fid = loop.add(title="stuck on limits")
    env = {**os.environ, "LOOPQ_HOME": str(loop.home), "LOOPQ_NOW": loop.now}
    run = subprocess.Popen([sys.executable, str(LOOPQ), "run", "--agent", "a",
                            "--config", str(loop.config_path)], env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    pidfile = loop.queue / "logs" / "a.pid"
    deadline = time.monotonic() + 10
    while not ((loop.wt("a") / "p.txt").exists() and pidfile.exists()):
        assert time.monotonic() < deadline, "agent did not start"
        time.sleep(0.05)

    res = loop.run("handoff", fid, "--to", "b")

    assert res.returncode == 0, res.stderr
    assert run.wait(timeout=10) != 0
    assert loop.state_of(fid) == "ready"
    assert loop.fragment(fid)[0]["assigned_to"] == "b"
    assert "p.txt" in git(loop.repo, "ls-tree", "--name-only", f"loop/{fid}").stdout


def test_retry_resets_attempts_and_requeues(loop):
    fid = loop.add(title="flaky")
    for _ in range(3):
        loop.tick("a")
        (loop.wt("a") / "bad.txt").write_text("FAIL\n")
        loop.write_result("a")
        loop.tick("a")
        loop.run("cooldown", "--agent", "a", "--clear")
    assert loop.state_of(fid) == "human"

    assert loop.run("retry", fid, "--note", "gate fixed upstream").returncode == 0

    front, body = loop.fragment(fid)
    assert loop.state_of(fid) == "ready" and front["attempts"] == 0
    assert "gate fixed upstream" in body


def test_pause_collects_but_takes_nothing_until_resume(loop):
    first = loop.add(title="one")
    loop.add(title="two")
    loop.tick("a")
    loop.write_result("a")
    loop.run("pause")

    assert loop.tick("a").returncode == 1
    assert loop.state_of(first) == "review"
    assert "paused" in loop.run("doctor").stdout

    loop.run("resume")
    assert loop.tick("a").returncode == 0


# provider-agnostic launcher, runs and sessions ------------------------------

FAKE_AGENT = (
    'echo "agent saw: $0"; cat .loop/FRAGMENT.md | head -1; '
    'echo hi > work.txt; mkdir -p .loop; '
    "printf -- \"---\\nstatus: done\\ncommit: 'feat: via run'\\n---\\nall good\\n\" > .loop/RESULT.md"
)


def use_command(loop, agent, script=FAKE_AGENT):
    loop.config["agents"][agent]["command"] = ["sh", "-c", script, "{prompt}"]
    loop.save_config()


def test_run_launches_the_agent_captures_output_and_collects(loop):
    use_command(loop, "a")
    fid = loop.add(title="launched")

    res = loop.run("run", "--agent", "a")

    assert res.returncode == 0, res.stderr
    assert loop.state_of(fid) == "review"
    [log] = list((loop.queue / "logs" / "runs").glob(f"{fid}-a-*.log"))
    assert "agent saw: Read .loop/FRAGMENT.md" in log.read_text()


def test_run_substitutes_model_in_agent_command(loop):
    loop.config["agents"]["a"]["model"] = "example-author-model"
    loop.config["agents"]["a"]["command"] = ["sh", "-c", FAKE_AGENT, "{model}"]
    loop.save_config()
    fid = loop.add(title="with model")

    res = loop.run("run", "--agent", "a")

    assert res.returncode == 0, res.stderr
    [log] = list((loop.queue / "logs" / "runs").glob(f"{fid}-a-*.log"))
    assert "agent saw: example-author-model" in log.read_text()


def test_run_rejects_missing_model_before_claiming(loop):
    loop.config["agents"]["a"]["command"] = ["sh", "-c", FAKE_AGENT, "{model}"]
    loop.save_config()
    fid = loop.add(title="needs model")

    res = loop.run("run", "--agent", "a")

    assert res.returncode != 0
    assert "uses {model} but no model is configured" in res.stderr
    assert loop.state_of(fid) == "ready"


def test_run_does_nothing_without_work(loop):
    use_command(loop, "a")

    assert loop.run("run", "--agent", "a").returncode == 1
    assert not (loop.queue / "logs" / "runs").exists() or not list((loop.queue / "logs" / "runs").iterdir())


def test_run_requeues_a_crashed_agent_and_cools_it_down(loop):
    loop.config["agents"]["a"]["cooldown_notice"] = "a crashed"
    use_command(loop, "a", "echo boom >&2; echo partial > p.txt; exit 3")
    fid = loop.add(title="crashes")

    res = loop.run("run", "--agent", "a")

    assert res.returncode == 3
    assert loop.state_of(fid) == "ready"
    assert "p.txt" in git(loop.repo, "ls-tree", "--name-only", "loop/tb-0001").stdout
    assert loop.notifications() == ["a crashed"]
    assert loop.tick("a").returncode == 1  # cooling down
    out = loop.run("runs", "--failed").stdout
    assert fid in out and "exit 3" in out


def test_run_gives_the_agent_no_input_so_a_prompt_fails_instead_of_hanging(loop):
    use_command(loop, "a", "read answer || exit 7; echo got $answer > p.txt")
    fid = loop.add(title="asks a question")

    env = {**os.environ, "LOOPQ_HOME": str(loop.home), "LOOPQ_NOW": loop.now}
    run = subprocess.Popen([sys.executable, str(LOOPQ), "run", "--agent", "a",
                            "--config", str(loop.config_path)], env=env,
                           stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)

    assert run.wait(timeout=20) == 7  # an open, silent stdin would hang here
    run.stdin.close()
    assert loop.state_of(fid) == "ready"


def test_runs_and_session_cover_both_launchers(loop):
    use_command(loop, "a")
    launched = loop.add(title="launched")
    external = loop.add(title="external")
    loop.run("run", "--agent", "a")
    # b is driven by an outside scheduler: only tick, plus a transcript file
    tdir = loop.tmp / "transcripts-b"
    tdir.mkdir()
    loop.config["agents"]["b"]["transcripts"] = str(tdir / "*.jsonl")
    loop.config["agents"]["b"]["kinds"] = ["work"]
    loop.save_config()
    loop.tick("b")
    (tdir / "s1.jsonl").write_text('{"msg": "working on it"}\n')
    stamp = datetime.fromisoformat("2026-09-25T10:10:00+00:00").timestamp()
    os.utime(tdir / "s1.jsonl", (stamp, stamp))
    loop.write_result("b", status="blocked", body="?")
    loop.tick("b", now="2026-09-25T10:30:00+00:00")

    out = loop.run("runs").stdout
    assert launched in out and external in out
    assert "a" in out and "b" in out

    assert "agent saw" in loop.run("session", launched).stdout
    out = loop.run("session", external).stdout
    assert "s1.jsonl" in out and "working on it" in out


def test_malformed_result_goes_to_the_operator_instead_of_crashing_every_tick(loop):
    fid = loop.add(title="bad result")
    loop.tick("a")
    (loop.wt("a") / ".loop" / "RESULT.md").write_text("status: done, no front matter\n")

    res = loop.tick("a")

    assert "Traceback" not in res.stderr
    assert loop.state_of(fid) == "human"
    assert "RESULT.md" in loop.fragment(fid)[1]


def test_human_steps_cannot_be_retried_or_requeued_into_ready(loop):
    fid = loop.add(title="operator step", kind="human")

    assert loop.run("retry", fid).returncode == 2
    assert "retry" not in loop.run("todo").stdout
    loop.run("resolve", fid, "--requeue", "--note", "not yet")
    assert loop.state_of(fid) == "human"


def test_human_steps_from_before_the_notified_field_still_notify(loop):
    dep = loop.add(title="dep")
    fid = loop.add(title="old step", kind="human", deps=[dep])
    path = loop.queue / "human" / f"{fid}.md"
    path.write_text(path.read_text().replace("notified: false\n", ""))
    (loop.queue / "ready" / f"{dep}.md").rename(loop.queue / "done" / f"{dep}.md")

    loop.tick("a")

    assert any("old step" in n for n in loop.notifications())


def test_session_transcript_globs_may_recurse(loop):
    tdir = loop.tmp / "sessions" / "2026" / "09" / "25"
    tdir.mkdir(parents=True)
    loop.config["agents"]["a"]["transcripts"] = str(loop.tmp / "sessions" / "**" / "*.jsonl")
    loop.save_config()
    fid = loop.add(title="deep")
    loop.tick("a")
    (tdir / "rollout.jsonl").write_text("deep line\n")
    stamp = datetime.fromisoformat("2026-09-25T10:05:00+00:00").timestamp()
    os.utime(tdir / "rollout.jsonl", (stamp, stamp))

    assert "deep line" in loop.run("session", fid).stdout


def test_doctor_folds_refusals_into_the_blocker_and_drops_them_once_it_clears(loop):
    git(loop.repo, "checkout", "-q", "tools")
    loop.tick("a")
    loop.tick("b")

    out = loop.run("doctor").stdout
    flat = " ".join(out.split())
    assert flat.count("last refused:") == 1 and "a 0s ago, b 0s ago" in flat
    assert "agent a:" not in flat

    git(loop.repo, "checkout", "-q", "main")
    res = loop.run("doctor")
    assert res.returncode == 0 and "refused" not in res.stdout


def test_milestones_shortens_long_waiting_lists(loop):
    loop.config["milestones"] = [{"id": f"m{i}", "source": "p", "after": []} for i in range(5)]
    loop.config["milestones"].append({"id": "last", "source": "p", "after": [f"m{i}" for i in range(5)]})
    loop.save_config()

    out = loop.run("milestones").stdout

    assert "waiting on 5 milestones" in out


def test_retry_can_move_a_fragment_to_another_tier(loop):
    fid = loop.add(title="hard stats", tier="standard")
    loop.tick("a")
    loop.write_result("a", status="blocked", body="too hard")
    loop.tick("a")

    assert loop.run("retry", fid, "--tier", "judgement", "--note", "needs judgement").returncode == 0

    front, body = loop.fragment(fid)
    assert loop.state_of(fid) == "ready" and front["tier"] == "judgement"
    assert "tier standard -> judgement" in body


def test_retry_rejects_an_unknown_tier(loop):
    fid = loop.add(title="x")
    loop.tick("a")
    loop.write_result("a", status="blocked")
    loop.tick("a")

    res = loop.run("retry", fid, "--tier", "genius")

    assert res.returncode != 0
    assert loop.state_of(fid) == "human"
