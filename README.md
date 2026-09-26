# loopq

loopq coordinates coding agents in separate Git worktrees. It assigns tasks,
collects results, gets another agent to review them, and integrates approved
changes into a dedicated base branch. It runs locally as a single Python script.

[![Watch loopq in action](https://asciinema.org/a/1266609.svg)](https://asciinema.org/a/1266609)

## Install

Requires Git, [uv](https://docs.astral.sh/uv/), and Python 3.11 or newer.

```sh
git clone https://github.com/alvagante/loopq.git
cd loopq
./manage.sh install
```

The installer creates a symlink in `~/.local/bin`, which must be on your `PATH`.
Keep the checkout in place. Preview the symlink with
`./manage.sh install --dry-run`. You can also run
`uv run --script /path/to/loopq.py` without installing.

## Set up a project

Install the [loopq-setup skill](skills/loopq-setup/SKILL.md) in your agent
harness and run it from your project's Git checkout, or follow the
[manual quickstart](docs/quickstart.md). Setup creates a base branch, one
worktree per agent identity, an integration worktree, and a config in
`~/.config/loopq/loops.d/`.

## Common workflows

Find a project and check what needs attention:

```sh
loopq loops
loopq doctor --loop PROJECT
loopq todo --loop PROJECT
```

For a manual author and reviewer cycle, add a fragment and run each agent in
the worktree and with the prompt printed by `tick`. Each agent reads
`.loop/FRAGMENT.md` and writes `.loop/RESULT.md`.

```sh
loopq add task.md --loop PROJECT
loopq tick --agent author --manual --loop PROJECT
# Run the author, then collect the result.
loopq tick --agent author --loop PROJECT
loopq tick --agent reviewer --manual --loop PROJECT
# Run the reviewer, then collect and integrate an approved result.
loopq tick --agent reviewer --loop PROJECT
```

Inspect a task or a stalled agent:

```sh
loopq show ID --loop PROJECT
loopq session ID --loop PROJECT
loopq why author --loop PROJECT
```

For automated sessions, configure an agent command and use `loopq run`, or
schedule all configured loops with one `loopq dispatch` cron entry:

```sh
loopq run --agent author --loop PROJECT
loopq dispatch --dry-run
```

See the [command reference](docs/commands.md) for every command, selection
rules, and options. The [configuration reference](docs/configuration.md)
covers runners and scheduling. Run `loopq help COMMAND` for CLI help.

[Release notes](CHANGELOG.md) · [License](LICENSE) · [Agent documentation](llms.txt)
