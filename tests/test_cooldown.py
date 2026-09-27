from conftest import git


def test_parked_work_returns_to_ready_and_cools_the_agent_down(loop):
    loop.config["agents"]["a"]["cooldown_notice"] = "switch account"
    loop.save_config()
    fid = loop.add(title="long job")
    loop.tick("a")
    (loop.wt("a") / "half.txt").write_text("half\n")
    loop.write_result("a", status="parked", body="Next: write the second half.")

    assert loop.tick("a").returncode == 1  # cooling down, takes nothing

    assert loop.state_of(fid) == "ready"
    assert "Next: write the second half." in loop.fragment(fid)[1]
    assert "half.txt" in git(loop.repo, "ls-tree", "--name-only", "loop/tb-0001").stdout
    assert loop.notifications() == ["switch account"]
    # another agent continues on the same branch
    assert loop.tick("b").returncode == 0
    assert (loop.wt("b") / "half.txt").exists()


def test_cooldown_expires_and_can_be_cleared_by_the_operator(loop):
    loop.add(title="one")
    loop.add(title="two")
    loop.tick("a")
    loop.write_result("a", status="parked")
    assert loop.tick("a").returncode == 1
    assert loop.tick("a", now="2026-09-25T11:59:00+00:00").returncode == 1

    assert loop.run("cooldown", "--agent", "a", "--clear").returncode == 0

    assert loop.tick("a", now="2026-09-25T11:59:00+00:00").returncode == 0


def test_cooldown_ends_on_its_own(loop):
    loop.add(title="one")
    loop.tick("a")
    loop.write_result("a", status="parked")
    loop.tick("a")

    assert loop.tick("a", now="2026-09-25T12:01:00+00:00").returncode == 0


def test_expired_lease_without_result_saves_partial_work_and_cools_down(loop):
    loop.config["agents"]["a"]["cooldown_notice"] = "switch account"
    loop.save_config()
    fid = loop.add(title="cut off")
    loop.tick("a")
    (loop.wt("a") / "partial.txt").write_text("partial\n")

    assert loop.tick("a", now="2026-09-25T14:01:00+00:00").returncode == 1

    assert loop.state_of(fid) == "ready"
    log = git(loop.repo, "log", "-1", "--format=%s", "loop/tb-0001").stdout.strip()
    assert log == "wip(tb-0001): partial"
    assert loop.notifications() == ["switch account"]
    assert not (loop.wt("a") / ".loop").exists()


def test_another_agents_expired_lease_is_requeued_without_cooling_anyone(loop):
    fid = loop.add(title="crashed")
    loop.tick("a")
    (loop.wt("a") / "partial.txt").write_text("partial\n")

    res = loop.tick("b", now="2026-09-25T14:01:00+00:00")

    assert res.returncode == 0
    assert loop.fragment(fid)[0]["claimed_by"] == "b"
    assert (loop.wt("b") / "partial.txt").exists()
    assert loop.notifications() == []


def test_cooldown_without_agent_shows_every_agent(loop):
    loop.run("cooldown", "--agent", "b", "--until", "2099-01-01T00:00:00+00:00")

    out = loop.run("cooldown").stdout

    assert "a available" in out
    assert "b cooling down until 2099-01-01T00:00:00+00:00" in out
    assert loop.run("cooldown", "--clear").returncode == 2
