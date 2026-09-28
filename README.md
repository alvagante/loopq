# loopq

loopq coordinates coding agents in separate Git worktrees. It assigns tasks,
collects results, gets another agent to review them, and integrates approved
changes into a dedicated base branch. It runs locally as a single Python script.

<a href="https://asciinema.org/a/1266672" target="_blank" rel="noopener noreferrer"><img src="https://asciinema.org/a/1266672.svg" alt="Watch loopq in action"></a>

## Install

Requires Git, [uv](https://docs.astral.sh/uv/), and Python 3.11 or newer.

```sh
git clone https://github.com/alvagante/loopq.git
cd loopq
./manage.sh install
```

The script creates a symlink in `~/.local/bin`, which must be on your `PATH`.
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

Find a project, make it the default for later commands, and check what
needs attention. `LOOPQ_LOOP=PROJECT`, working inside one of the loop's
worktrees, or `--loop PROJECT` select a loop too:

```sh
loopq loops
loopq use PROJECT
loopq doctor
loopq todo
```

For a manual author and reviewer cycle, add a fragment and run each agent in
the worktree and with the prompt printed by `tick`. Each agent reads
`.loop/FRAGMENT.md` and writes `.loop/RESULT.md`.

```sh
loopq add task.md
loopq tick --agent author --manual
# Run the author, then collect the result.
loopq tick --agent author
loopq tick --agent reviewer --manual
# Run the reviewer, then collect and integrate an approved result.
loopq tick --agent reviewer
```

Inspect a task or a stalled agent:

```sh
loopq show ID
loopq session ID
loopq why author
```

For automated sessions, configure an agent command and use `loopq run`, or
schedule all configured loops with one `loopq dispatch` cron entry:

```sh
loopq run --agent author
loopq dispatch --dry-run
```

See the [command reference](docs/commands.md) for every command, selection
rules, and options. The [configuration reference](docs/configuration.md)
covers runners and scheduling, and a [multi-agent example](docs/examples/multi-agent.yaml)
shows several harnesses and one harness with two models. Run
`loopq help COMMAND` for CLI help.

[Release notes](CHANGELOG.md) · [License](LICENSE) · [Agent documentation](llms.txt)
