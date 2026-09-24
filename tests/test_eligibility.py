def test_fragment_waits_for_its_deps(loop):
    first = loop.add(title="first")
    second = loop.add(title="second", deps=[first])
    loop.config["agents"]["a"]["kinds"] = ["work"]
    loop.save_config()
    loop.tick("a")
    assert loop.fragment(first)[0]["claimed_by"] == "a"

    assert loop.tick("b").returncode == 1  # second waits on first
    assert loop.state_of(second) == "ready"


def test_agent_takes_only_its_tiers_and_kinds(loop):
    loop.config["agents"]["a"]["tiers"] = ["mechanical"]
    loop.config["agents"]["b"]["kinds"] = ["review"]
    loop.save_config()
    hard = loop.add(title="hard", tier="judgement")
    easy = loop.add(title="easy", tier="mechanical")

    assert loop.tick("b").returncode == 1
    assert loop.tick("a").returncode == 0
    assert loop.fragment(easy)[0]["claimed_by"] == "a"
    assert loop.state_of(hard) == "ready"


def test_reviews_come_before_new_work(loop):
    loop.add(title="work one")
    loop.tick("a")
    (loop.wt("a") / "x.txt").write_text("x\n")
    loop.write_result("a", commit="feat: x")
    loop.add(title="work two")
    loop.tick("a")  # collects work one, takes work two

    assert loop.tick("b").returncode == 0
    claimed = [i for i in loop.ids_in("claimed") if loop.fragment(i)[0]["claimed_by"] == "b"]
    assert loop.fragment(claimed[0])[0]["kind"] == "review"
