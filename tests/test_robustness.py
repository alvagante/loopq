import os


def install_failing_hook(loop):
    hook = loop.repo / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\necho 'hook says no' >&2\nexit 1\n")
    os.chmod(hook, 0o755)


def test_git_failure_during_collect_parks_the_fragment_with_the_operator(loop):
    fid = loop.add(title="x")
    loop.tick("a")
    (loop.wt("a") / "x.txt").write_text("x\n")
    loop.write_result("a", commit="feat: x")
    install_failing_hook(loop)

    res = loop.tick("a")

    assert res.returncode == 1, res.stderr
    assert loop.state_of(fid) == "human"
    assert "hook says no" in loop.fragment(fid)[1]
    assert any(fid in n for n in loop.notifications())
    assert loop.tick("a").returncode == 1  # the agent is not wedged


def test_git_failure_while_expiring_a_lease_does_not_wedge_the_queue(loop):
    fid = loop.add(title="x")
    loop.tick("a")
    (loop.wt("a") / "x.txt").write_text("x\n")
    install_failing_hook(loop)

    res = loop.tick("b", now="2026-09-25T14:01:00+00:00")

    assert res.returncode == 1, res.stderr
    assert loop.state_of(fid) == "human"
