# Set up loopq with a skill

The setup and day-to-day operator workflow lives in the
[loopq skill](../skills/loopq/SKILL.md). `./manage.sh install` asks whether to
symlink that skill into the global skill directories for agent harnesses on
your `PATH`. Use `--skill` to install without asking, or install
`skills/loopq` with your harness's skill manager. Then invoke `loopq` from
your project's Git checkout. For Codex, you can also ask it to install the
skill from `alvagante/loopq`, path `skills/loopq`, then invoke `$loopq`. Until
the repository is public, give the harness the path to a local loopq checkout.

The skill routes setup, enqueueing work, monitoring, acting on blockers, and
running or scheduling ticks. For setup it asks about roles, models, harnesses
and scheduling, presents the exact Git and YAML changes for approval, then
runs and verifies. The [quickstart](quickstart.md) remains available for
manual setup.
