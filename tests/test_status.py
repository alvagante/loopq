def test_status_shows_counts_claims_cooldowns_human_items_and_briefs(loop):
    loop.add(title="one")
    loop.add(title="two")
    loop.add(title="three")
    loop.tick("a")
    loop.tick("b")
    loop.write_result("b", status="blocked", body="?")
    loop.tick("b")  # two goes to human; b takes three
    loop.run("cooldown", "--agent", "b", "--until", "2026-09-25T15:00:00+00:00")
    (loop.queue / "briefs" / "m1.md").write_text("brief\n")

    out = loop.run("status").stdout

    assert "ready 0  claimed 2  review 0  human 1  done 0" in out
    assert "tb-0001 claimed by a until 2026-09-25T14:00:00+00:00: one" in out
    assert "tb-0002 human: two" in out
    assert "cooldown b until 2026-09-25T15:00:00+00:00" in out
    assert "brief m1 unread" in out
