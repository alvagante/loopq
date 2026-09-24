import yaml


def write_out(loop, agent, name, **front):
    body = front.pop("body", "## Goal\nx\n## Read first\nx\n## Files\nx\n## Acceptance\nx\n")
    d = loop.wt(agent) / ".loop" / "out" / "fragments"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.md").write_text("---\n" + yaml.safe_dump(front) + "---\n" + body)


def with_milestones(loop):
    loop.config["milestones"] = [
        {"id": "m1", "source": "plan.md#slice-1", "after": []},
        {"id": "m2", "source": "plan.md#slice-2", "after": ["m1"]},
    ]
    loop.save_config()


def test_ready_milestone_gets_a_decompose_fragment_whose_output_is_enqueued(loop):
    with_milestones(loop)

    assert loop.tick("a").returncode == 0

    [dec] = loop.ids_in("claimed")
    front, _ = loop.fragment(dec)
    assert (front["kind"], front["tier"], front["milestone"]) == ("decompose", "judgement", "m1")
    assert "plan.md#slice-1" in (loop.wt("a") / ".loop" / "FRAGMENT.md").read_text()
    assert not [i for i in loop.ids_in("ready") if loop.fragment(i)[0]["milestone"] == "m2"]

    write_out(loop, "a", "schema", title="schema", kind="work", tier="standard", deps=[])
    write_out(loop, "a", "validator", title="validator", kind="work", tier="standard", deps=["schema"])
    write_out(loop, "a", "token", title="create token", kind="human", tier="standard", deps=[])
    loop.write_result("a")

    loop.tick("a")

    assert loop.state_of(dec) == "done"
    by_title = {loop.fragment(i)[0]["title"]: i for s in ("ready", "claimed", "human") for i in loop.ids_in(s)}
    assert loop.fragment(by_title["validator"])[0]["deps"] == [by_title["schema"]]
    assert loop.fragment(by_title["validator"])[0]["milestone"] == "m1"
    assert loop.state_of(by_title["create token"]) == "human"
    assert any("create token" in n for n in loop.notifications())
    assert loop.fragment(by_title["schema"])[0]["claimed_by"] == "a"


def test_invalid_decompose_output_goes_back_with_the_errors(loop):
    with_milestones(loop)
    loop.tick("a")
    [dec] = loop.ids_in("claimed")
    write_out(loop, "a", "bad", title="bad", kind="work", deps=["nope"])
    loop.write_result("a")

    loop.tick("a")

    front, body = loop.fragment(dec)
    assert front["attempts"] == 1
    assert "tier" in body and "nope" in body
    assert not [i for s in ("ready", "claimed") for i in loop.ids_in(s) if loop.fragment(i)[0]["title"] == "bad"]


def finish_milestone_with_one_human_step(loop):
    """m1 decomposes into a single human step, which the operator resolves."""
    loop.tick("a")
    write_out(loop, "a", "token", title="create token", kind="human", tier="standard", deps=[])
    loop.write_result("a")
    loop.tick("a")
    [human] = loop.ids_in("human")
    assert loop.run("resolve", human, "--done", "--note", "token created").returncode == 0
    return human


def test_complete_milestone_gets_a_brief_that_is_filed_and_announced(loop):
    with_milestones(loop)
    human = finish_milestone_with_one_human_step(loop)
    assert "token created" in loop.fragment(human)[1]

    assert loop.tick("a").returncode == 0  # m2's decompose ranks above the brief
    assert loop.tick("b").returncode == 0
    [brief] = [i for i in loop.ids_in("claimed") if loop.fragment(i)[0]["claimed_by"] == "b"]
    assert loop.fragment(brief)[0]["kind"] == "brief"
    assert str(loop.queue / "done" / f"{human}.md") in (loop.wt("b") / ".loop" / "FRAGMENT.md").read_text()
    loop.write_result("b", body="m1 produced a token.")
    loop.tick("b")

    assert (loop.queue / "briefs" / "m1.md").read_text().strip() == "m1 produced a token."
    assert any("m1" in n for n in loop.notifications())


def test_held_milestone_blocks_its_successors_until_acknowledged(loop):
    with_milestones(loop)
    loop.config["milestones"][0]["hold"] = True
    loop.save_config()
    finish_milestone_with_one_human_step(loop)
    loop.tick("a")
    loop.write_result("a", body="brief")
    assert loop.tick("a").returncode == 1  # m2 held back

    assert loop.run("ack", "m1").returncode == 0

    assert loop.tick("a").returncode == 0
    [dec] = loop.ids_in("claimed")
    assert loop.fragment(dec)[0]["milestone"] == "m2"


def test_brief_followup_enqueues_a_work_fragment_that_reads_the_brief(loop):
    with_milestones(loop)
    loop.config["brief_followup"] = {
        "title": "Fold the brief into the plan Status",
        "tier": "mechanical",
        "goal": "Add the brief as a dated Status entry.",
    }
    loop.save_config()
    finish_milestone_with_one_human_step(loop)
    loop.tick("a")  # m2 decompose
    loop.tick("b")  # m1 brief
    loop.write_result("b", body="brief")
    loop.tick("b")

    follow = [i for s in ("ready", "claimed") for i in loop.ids_in(s)
              if loop.fragment(i)[0]["title"] == "Fold the brief into the plan Status"]
    assert len(follow) == 1
    front, body = loop.fragment(follow[0])
    assert (front["kind"], front["tier"], front["milestone"]) == ("work", "mechanical", "m1")
    assert str(loop.queue / "briefs" / "m1.md") in body
