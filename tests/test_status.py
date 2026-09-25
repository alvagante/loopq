import re


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

    assert re.search(r"ready 0\s+\S+ claimed 2\s+\S+ review 0\s+\S+ human 1\s+\S+ done 0", out)
    assert re.search(r"tb-0001\s+a\s+2026-09-25T14:00:00\+00:00 \(in 4h\)\s+one", out)
    assert "tb-0002 human: two" in out
    assert "cooldown b until 2026-09-25T15:00:00+00:00" in out
    assert "brief m1 unread" in out
