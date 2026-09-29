# loopq

**Your coding agents, all the loops you want: assign, review, integrate. Locally.**

Run as many project loops as you need, each with its own agents, worktrees, and
queue. Work is assigned, reviewed by a second identity, and integrated when it
passes, on your machine, under your control.

loopq coordinates coding agents in separate Git worktrees. It assigns tasks,
collects results, gets another agent to review them, and integrates approved
changes into a dedicated base branch. It runs locally as a single Python script.

<a href="https://asciinema.org/a/1266942" target="_blank" rel="noopener noreferrer"><img src="https://asciinema.org/a/1266942.svg" alt="Watch loopq in action"></a>

## Install

Requires Git, [uv](https://docs.astral.sh/uv/), and Python 3.11 or newer.
Install uv through your package manager or follow its linked instructions.

```sh
git clone https://github.com/alvagante/loopq.git
cd loopq
./manage.sh install
loopq version
```

The script creates a symlink in `~/.local/bin`, which must be on your `PATH`.
Keep the checkout in place. Preview with `./manage.sh install --dry-run`.
You can also run `uv run --script /path/to/loopq.py` without installing.

On a TTY, install also asks whether to symlink the
[loopq skill](skills/loopq/SKILL.md) into skill directories for agent
harnesses found on `PATH` (Claude Code, Codex, Cursor, OpenCode, and others).
Use `--skill` or `--no-skill` to skip the prompt. That skill is the agent
entry point for creating a loop, enqueueing work, monitoring, unblocking, and
running or scheduling ticks. Invoke it as `loopq` from the project's Git
checkout (or ask the harness to use the skill by name). For Codex you can
install from `alvagante/loopq`, path `skills/loopq`, then invoke `$loopq`.

In a Swamp repository, install the same skill for that repository with:

```sh
swamp extension pull @alvagante/loopq
```

The Swamp extension provides the skill. Install the Loopq CLI separately to
run its commands.

### Docker image

Build the image locally to inspect your loops. Mount the config directory and
queue data so the container can find them:

```sh
docker build -t loopq:local .
docker run --rm --user "$(id -u):$(id -g)" \
  --mount "type=bind,source=$HOME/.config/loopq/loops.d,target=/config,readonly" \
  --mount "type=bind,source=$HOME/.loops,target=/data" \
  -e LOOPQ_CONFIG_DIR=/config \
  loopq:local status --all
```

The release workflow publishes versioned images to
`ghcr.io/example42/loopq` and `DOCKERHUB_USERNAME/loopq` when a version tag
is pushed. Commands that run agents also need their binaries and access to
the configured worktrees inside the container.

## Set up a project

Start in the project's Git checkout. Your current branch stays in place.
Loopq uses a separate base branch, one worktree per agent identity, and an
integration worktree:

```text
project/                   your checkout
project-loop-author/       author worktree
project-loop-reviewer/     reviewer worktree
project-loop-integration/  integration worktree
```

Every setup needs two agent identities for cross-agent review, even if they
share a harness. Choose `main`, `HEAD`, or another commit as the starting
ref; uncommitted files are excluded. Keep the base branch unchecked out while
loopq runs. Configs live in `~/.config/loopq/loops.d/` and queue data in
`~/.loops/` by default.

### Agent-guided (recommended)

With the skill installed, open the project checkout in your harness and
invoke `loopq` (or ask it to set up a loopq project). The skill inspects the
repo, asks about roles, models, harnesses, and optional scheduling, then
shows the exact Git commands and YAML for approval before applying them. It
verifies with `loopq loops` and `loopq doctor`. Details:
[skill](skills/loopq/SKILL.md) and [setup prompt](docs/setup-prompt.md).

### CLI-assisted

`loopq create` writes a starter config and prints the branch and worktree
commands. Review the agent roles, commands, gate, and paths. Replace
`START_REF` with the commit to start from, then run the printed commands.
`loopq create --project NAME` writes a separate loop config for the same
repository. Verify with `loopq --loop NAME doctor`.

### Manual

Follow the [quickstart](docs/quickstart.md) to create the base branch,
worktrees, and config yourself.

Loopq advances only its base branch. Merge that branch into your delivery
branch when ready. To bring newer `main` commits into future loop work,
follow the [quickstart update steps](docs/quickstart.md#keeping-the-loop-current).
Multiple loops in one repository need distinct names, prefixes, base
branches, and worktree paths.

## Common workflows

A work fragment moves from `ready` to `claimed`. After the author finishes,
loopq commits it on `loop/ID` and requests review from another agent. An
approved review and passing gate move it to `done` and advance the loop base.
Work needing an operator decision goes to `human`. The queue files live
outside the Git checkout.

Use the [loopq skill](skills/loopq/SKILL.md) from your agent for these jobs,
or run the CLI yourself. Find a project, make it the default for later
commands, and check what needs attention. `LOOPQ_LOOP=PROJECT`, working
inside one of the loop's worktrees, or `--loop PROJECT` select a loop too:

```sh
loopq loops
loopq use PROJECT
loopq doctor
loopq todo
```

To return to the combined view after saving a project, run `loopq use --all`.
For a combined view just once, run `loopq status --all` or `loopq doctor --all`.
`LOOPQ_LOOP` and the current worktree can still select a project after the
saved choice is cleared.

Create a task template outside the agent worktrees, edit its Goal, Files and
Acceptance sections, then enqueue it. `add` copies it into the queue:

```sh
loopq new task.md --title "Add a greeting" --tier standard
loopq add task.md
loopq list --state ready
```

For a manual author and reviewer cycle, use the queued task and run each agent
in the worktree with the prompt printed by `tick`. Each agent reads
`.loop/FRAGMENT.md` and writes `.loop/RESULT.md`.

```sh
loopq tick --agent author --manual
# Run the author, then collect the result.
loopq tick --agent author
loopq tick --agent reviewer --manual
# Run the reviewer, then collect and integrate an approved result.
loopq tick --agent reviewer
```

Inspect a task or a stalled agent:

```sh
loopq runs
loopq runs --failed
loopq list --state claimed
loopq show ID
loopq session ID
loopq why author
loopq stats
```

Complete a human step with `loopq resolve ID --done`. After fixing blocked
work, use `loopq retry ID`. Preview archival with `loopq prune --dry-run`.

For automated sessions, review an agent command and use `loopq run`, or
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
