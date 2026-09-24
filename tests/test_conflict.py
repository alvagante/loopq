from conftest import git


def move_base(loop, filename, content, message):
    iw = loop.wt("int")
    git(iw, "checkout", "-q", "tools")
    (iw / filename).write_text(content)
    git(iw, "add", "-A")
    git(iw, "commit", "-q", "-m", message)
    git(iw, "checkout", "-q", "--detach")


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

    (loop.wt("b") / "app.txt").write_text("line from base\nline from work\n")
    loop.write_result("b", commit="feat: edit app")
    loop.tick("b")

    assert loop.state_of(fid) == "done"
    assert loop.state_of(conflict[0]) == "done"
    assert git(loop.repo, "show", "tools:app.txt").stdout == "line from base\nline from work\n"
    subjects = git(loop.repo, "log", "--format=%s", "tools").stdout.splitlines()
    assert subjects[:2] == ["feat: edit app", "base edits app"]
