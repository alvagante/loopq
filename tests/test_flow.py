from conftest import git


def test_done_work_is_committed_gated_and_sent_to_another_agent_for_review(loop):
    fid = loop.add(title="add feature", milestone="m1")
    loop.tick("a")
    (loop.wt("a") / "feature.txt").write_text("hello\n")
    loop.write_result("a", commit="feat: add feature")

    res = loop.tick("a")

    assert res.returncode == 1, res.stderr  # nothing left that a may take
    assert loop.state_of(fid) == "review"
    log = git(loop.repo, "log", "-1", "--format=%s%n%b", "loop/tb-0001").stdout
    assert "feat: add feature" in log
    assert "Loop-Fragment: tb-0001" in log
    assert "Loop-Agent: a" in log
    assert not (loop.wt("a") / ".loop").exists()
    reviews = [i for i in loop.ids_in("ready") if loop.fragment(i)[0]["kind"] == "review"]
    assert len(reviews) == 1
    review, _ = loop.fragment(reviews[0])
    assert review["target"] == fid
    assert review["author"] == "a"
    assert review["tier"] == "standard"
    assert review["milestone"] == "m1"

    assert loop.tick("b").returncode == 0
    assert loop.state_of(reviews[0]) == "claimed"
    head = git(loop.wt("b"), "rev-parse", "HEAD").stdout
    assert head == git(loop.repo, "rev-parse", "loop/tb-0001").stdout


def do_work(loop, agent, title, filename, content="hello\n"):
    fid = loop.add(title=title)
    assert loop.tick(agent).returncode == 0
    (loop.wt(agent) / filename).write_text(content)
    loop.write_result(agent, commit=f"feat: {title}")
    loop.tick(agent)
    return fid


def test_approved_review_integrates_the_work_onto_a_moved_base(loop):
    fid = do_work(loop, "a", "add feature", "feature.txt")
    # the base moves after the work branched off
    git(loop.wt("int"), "checkout", "-q", "tools")
    (loop.wt("int") / "other.txt").write_text("other\n")
    git(loop.wt("int"), "add", "-A")
    git(loop.wt("int"), "commit", "-q", "-m", "other change")
    git(loop.wt("int"), "checkout", "-q", "--detach")
    assert loop.tick("b").returncode == 0
    review = loop.ids_in("claimed")[0]
    loop.write_result("b", verdict="approve")

    loop.tick("b")

    assert loop.state_of(fid) == "done"
    assert loop.state_of(review) == "done"
    subjects = git(loop.repo, "log", "--format=%s", "tools").stdout.splitlines()
    assert subjects[:2] == ["feat: add feature", "other change"]
    assert git(loop.repo, "show", "tools:feature.txt").stdout == "hello\n"


def test_review_asking_for_changes_sends_the_work_back_with_findings(loop):
    fid = do_work(loop, "a", "add feature", "feature.txt")
    loop.tick("b")
    loop.write_result("b", verdict="changes", body="1. Missing test.")

    loop.tick("b")

    # the reviewer is free again and takes the returned work on its branch
    assert loop.state_of(fid) == "claimed"
    front, body = loop.fragment(fid)
    assert front["claimed_by"] == "b"
    assert front["attempts"] == 1
    assert "1. Missing test." in body
    assert (loop.wt("b") / "feature.txt").exists()
    assert "1. Missing test." in (loop.wt("b") / ".loop" / "FRAGMENT.md").read_text()
    assert "feature.txt" not in git(loop.repo, "ls-tree", "--name-only", "tools").stdout


def test_failing_gate_requeues_with_the_failure_and_goes_to_human_after_three(loop):
    fid = loop.add(title="broken")
    assert loop.tick("a").returncode == 0
    for attempt in (1, 2, 3):
        (loop.wt("a") / "bad.txt").write_text(f"FAIL {attempt}\n")
        loop.write_result("a", commit="feat: broken")
        loop.tick("a")  # collects, and re-reserves while attempts remain
        assert loop.fragment(fid)[0]["attempts"] == attempt
        if attempt < 3:
            assert loop.state_of(fid) == "claimed"
            prompt = (loop.wt("a") / ".loop" / "FRAGMENT.md").read_text()
            assert "gate command failed" in prompt
    assert loop.state_of(fid) == "human"
    assert any(fid in n for n in loop.notifications())


def test_blocked_result_goes_to_human_with_the_question(loop):
    fid = loop.add(title="needs decision")
    loop.tick("a")
    loop.write_result("a", status="blocked", body="Which port should it use?")

    assert loop.tick("a").returncode == 1

    assert loop.state_of(fid) == "human"
    assert "Which port should it use?" in loop.fragment(fid)[1]
    assert any(fid in n for n in loop.notifications())


def test_gate_rejects_forbidden_characters_in_added_lines(loop):
    fid = loop.add(title="dashy")
    loop.tick("a")
    (loop.wt("a") / "prose.md").write_text("a \u2014 b\n")
    loop.write_result("a", commit="docs: dashy")

    loop.tick("a")

    assert "forbidden characters" in loop.fragment(fid)[1]
    assert loop.fragment(fid)[0]["attempts"] == 1
