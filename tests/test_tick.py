def test_tick_with_empty_queue_exits_1_and_reserves_nothing(loop):
    res = loop.tick("a")
    assert res.returncode == 1
    assert not (loop.wt("a") / ".loop" / "FRAGMENT.md").exists()


def test_tick_reserves_ready_work_and_prepares_the_agent_worktree(loop):
    fid = loop.add(title="first thing")
    assert fid == "tb-0001"

    res = loop.tick("a")

    assert res.returncode == 0, res.stderr
    assert loop.state_of(fid) == "claimed"
    front, _ = loop.fragment(fid)
    assert front["claimed_by"] == "a"
    assert front["lease_until"] == "2026-09-25T14:00:00+00:00"
    assert front["branch"] == "loop/tb-0001"
    from conftest import git
    assert git(loop.wt("a"), "branch", "--show-current").stdout.strip() == "loop/tb-0001"
    prompt = (loop.wt("a") / ".loop" / "FRAGMENT.md").read_text()
    assert "Project rules go here." in prompt
    assert "first thing" in prompt
    assert "RESULT.md" in prompt


def test_agent_holding_a_live_claim_gets_nothing_more(loop):
    first = loop.add(title="first")
    second = loop.add(title="second")
    assert loop.tick("a").returncode == 0

    res = loop.tick("a", now="2026-09-25T11:00:00+00:00")

    assert res.returncode == 1
    assert loop.state_of(first) == "claimed"
    assert loop.state_of(second) == "ready"


def test_tick_refuses_while_the_base_branch_is_checked_out(loop):
    from conftest import git
    loop.add(title="x")
    git(loop.repo, "checkout", "-q", "tools")

    res = loop.tick("a")

    assert res.returncode == 2
    assert "tools is checked out" in res.stderr
    assert loop.ids_in("claimed") == []


def test_manual_tick_prints_where_to_work_and_what_to_paste(loop):
    loop.add(title="x")

    res = loop.tick("a", "--manual")

    assert res.returncode == 0
    assert str(loop.wt("a")) in res.stdout
    assert "Read .loop/FRAGMENT.md in this worktree and follow it exactly." in res.stdout


def test_manual_tick_says_when_there_is_nothing(loop):
    res = loop.tick("a", "--manual")

    assert res.returncode == 1
    assert "nothing for a" in res.stdout
