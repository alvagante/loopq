# Set up loopq with a skill

The setup workflow is now the [loopq-setup skill](../skills/loopq-setup/SKILL.md).
Install the `skills/loopq-setup` directory with your agent harness's skill
manager, then invoke `loopq-setup` from your project's Git checkout. For
Codex, ask it to install the skill from `alvagante/loopq`, path
`skills/loopq-setup`, then invoke `$loopq-setup`. Until the repository is
public, give the harness the path to a local loopq checkout.

The skill asks about roles, models, harnesses and scheduling, presents the
exact Git and YAML changes for approval, then runs and verifies the setup.
The [quickstart](quickstart.md) remains available for manual setup.
