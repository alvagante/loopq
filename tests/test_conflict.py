from conftest import git


def move_base(loop, filename, content, message):
    iw = loop.wt("int")
    git(iw, "checkout", "-q", "tools")
    (iw / filename).write_text(content)
    git(iw, "add", "-A")
    git(iw, "commit", "-q", "-m", message)
    git(iw, "checkout", "-q", "--detach")


def resolve_conflict(loop, lines, commit="feat: edit app"):
    (loop.wt("b") / "app.txt").write_text(lines)
    loop.write_result("b", commit=commit)


def test_conflicting_integration_becomes_a_conflict_fragment_then_lands(loop):
    fid = loop.add(title="edit app")
    loop.tick("a")
    (loop.wt("a") / "app.txt").write_text("line from work\n")
    loop.write_result("a", commit="feat: edit app")
    loop.tick("a")
    move_base(loop, "app.txt", "line from base\n", "base edits app")
    loop.tick("b")
    loop.write_result("b", verdict="approve")

    loop.tick("b")  # integration conflicts; b then takes the conflict fragment

    assert loop.state_of(fid) == "review"
    conflict = [i for i in loop.ids_in("claimed") if loop.fragment(i)[0]["kind"] == "conflict"]
    assert len(conflict) == 1
    assert "<<<<<<<" in (loop.wt("b") / "app.txt").read_text()

    resolve_conflict(loop, "line from base\nline from work\n")
    loop.tick("b")

    assert loop.state_of(fid) == "done"
    assert loop.state_of(conflict[0]) == "done"
    assert git(loop.repo, "show", "tools:app.txt").stdout == "line from base\nline from work\n"
    subjects = git(loop.repo, "log", "--format=%s", "tools").stdout.splitlines()
    assert subjects[:2] == ["feat: edit app", "base edits app"]


def test_conflict_resolved_out_of_band_integrates_as_a_noop(loop):
    # cc-0081..cc-0087: the conflict fragment exists while the operator fixes
    # the base out of band, so by the time the worker reports done the branch
    # is already contained in the base. Integration must land the target as
    # done (no rebase, no gate over an empty diff) instead of churning out
    # another conflict fragment.
    fid = loop.add(title="edit app")
    loop.tick("a")
    (loop.wt("a") / "app.txt").write_text("line from work\n")
    loop.write_result("a", commit="feat: edit app")
    loop.tick("a")
    move_base(loop, "app.txt", "line from base\n", "base edits app")
    loop.tick("b")
    loop.write_result("b", verdict="approve")

    loop.tick("b")  # integration conflicts; b takes the conflict fragment

    conflict = [i for i in loop.ids_in("claimed") if loop.fragment(i)[0]["kind"] == "conflict"][0]
    # Out of band: a merge commit on the base now carries the branch's change.
    move_base(loop, "app.txt", "line from base\nline from work\n", "merge edit app")

    resolve_conflict(loop, "line from base\nline from work\n")
    loop.tick("b")  # the squash merge is empty; integration finds containment

    assert loop.state_of(fid) == "done"
    assert loop.state_of(conflict) == "done"
    subjects = git(loop.repo, "log", "--format=%s", "tools").stdout.splitlines()
    assert subjects[0] == "merge edit app"
