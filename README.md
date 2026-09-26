# loopq

A local CLI for coordinating AI coding agents in short sessions. loopq assigns
fragments to separate Git worktrees, checks results, requests review from a
different agent, and integrates approved changes into a dedicated base branch.
Agents read `.loop/FRAGMENT.md` and write `.loop/RESULT.md`; loopq handles
claims, leases, gates, commits and integration.

loopq is a single Python script with inline dependencies. It runs locally and
does not require a hosted service.
For agents, [llms.txt](llms.txt) indexes the docs and [AGENTS.md](AGENTS.md)
explains how to work on this repository.

## Install

Requires Git, [uv](https://docs.astral.sh/uv/), and a Python version supported
by the script (3.11 or newer). Install from a checkout:

```sh
git clone https://github.com/alvagante/loopq.git
cd loopq
./manage.sh install
```

The helper prints the exact symlink it will create in `~/.local/bin` and
refuses to replace an existing path. Keep the checkout in place. Make sure
`~/.local/bin` is on `PATH`. Use `./manage.sh install --dry-run` to preview,
or `./manage.sh uninstall` to remove only that symlink. Set `LOOPQ_BIN_DIR`
to use another bin directory. Uninstall leaves queue data, configs, worktrees
and the checkout alone.

You can also run `uv run --script /path/to/loopq.py` without installing it.
The code is licensed under [MIT](LICENSE).
See the [changelog](CHANGELOG.md) for release notes.

## Start a loop

Install the [loopq-setup skill](skills/loopq-setup/SKILL.md) in your agent
harness, then invoke it from your project's Git checkout. In Codex, ask it to
install the skill from `alvagante/loopq`, path `skills/loopq-setup`, then use
`$loopq-setup`. The skill
works even if loopq is not installed yet. It asks which roles, models and
harnesses you want, presents the Git worktrees, config and any schedule for
approval, then runs and verifies the setup.

In your project's Git repository, create one base branch and a separate
worktree for each agent identity, plus one integration worktree. Put a YAML
config in `~/.config/loopq/loops.d/` that maps the identities to those paths.
Add a fragment, then start your agent harness in the worktree printed by
`loopq tick --manual`, using the printed prompt. loopq writes the task to
`.loop/FRAGMENT.md`; the agent writes `.loop/RESULT.md`. A second identity
reviews the result before loopq advances the base branch. Your normal branch
is not moved.

For manual setup, follow the [project quickstart](docs/quickstart.md) for the
exact commands and harness handoff. The
[configuration reference](docs/configuration.md) covers unattended runners,
milestones and safety-related options.

## Commands

By default, loopq scans `~/.config/loopq/loops.d/` for `.yaml` and `.yml`
configs. Put one config or symlink per project there. Run `loopq loops` to see
what it found, then `loopq status` to inspect every loop. Bare `loopq` runs
`doctor` across all loops. `status`, `todo`, `milestones`, and read-only
`cooldown --agent NAME` show each loop. `runs` combines sessions across loops
and applies `--limit` to the combined list (30 by default). `show`, `history`,
and `session` find a unique fragment ID across loops. Use `--loop PROJECT` for
one loop, or when an ID occurs in multiple loops. `why` requires a loop when
multiple are discovered because its ready-fragment table can be long.
Other commands that change state require `--loop PROJECT` when multiple loops
exist. `dispatch` always scans every loop.
`--config FILE` or `LOOPQ_CONFIG` still select an explicit file. Set
`LOOPQ_CONFIG_DIR` or pass `--config-dir DIR` for another directory.
The queue lives in
`$LOOPQ_HOME/<project>/` (default `~/.loops`).
Run `loopq help` or `loopq -h` for the full command overview, and
`loopq help COMMAND` or `loopq COMMAND -h` for its options.

Output uses [Rich](https://github.com/Textualize/rich): colour, tables and
rendered fragment Markdown on a terminal; plain text at 220 columns (or
`COLUMNS`) when piped. `NO_COLOR` and `FORCE_COLOR` are honoured.

What needs me:

| Command | Purpose |
|---|---|
| `doctor` | Blockers first (base branch checked out, refused ticks, expired leases, dirty or missing worktrees, pause, cooldowns), then items and briefs waiting on you. Exit 1 when anything needs attention. |
| `todo` | Your inbox: human steps you can do now (with the commands to close them), human steps still waiting on the loop and on which deps, unread briefs. |
| `resolve ID --done\|--requeue [--note T]` | Close or return a human fragment. |
| `ack MILESTONE` | Mark a brief read and release a `hold`. |

Inspect and debug:

| Command | Purpose |
|---|---|
| `help [COMMAND]` | Show the full overview or detailed help for one command. |
| `loops` | List discovered project names and config paths. |
| `status` | Counts, claims, human items, cooldowns, unread briefs. |
| `milestones` | Progress per milestone and what each one waits on. |
| `show ID` | Fragment, dependency states, commits on its branch and in the base, history. |
| `history ID` | Every transition of a fragment, from `logs/events.jsonl`. |
| `why AGENT` | Why an agent takes nothing: busy, refused, paused, cooldown, and per ready fragment the kind, tier or deps that exclude it. |
| `runs [--agent A] [--failed] [--limit N]` | Agent sessions (one per claim) with outcome and exit code, whatever launched them. |
| `session ID [--paths]` | Full output of each session that worked a fragment: the log `run` captured, or the agent's transcript files from its claim window. |

Act:

| Command | Purpose |
|---|---|
| `tick --agent A [--manual]` | Collect A's finished fragment, then reserve the next one. Exit 0 = work reserved, 1 = nothing, 2 = refused. |
| `run --agent A` | `tick`, then launch A's `command` in its worktree, capture its output to `logs/runs/`, and collect as soon as it exits. A non-zero exit without a result requeues the fragment with its partial work and cools A down. Exits 1 without launching while A's previous run is alive. |
| `dispatch --config-dir DIR [--dry-run]` | Check every `.yaml` or `.yml` loop config in `DIR`. Start command agents or trigger matching Orca automations when their `cron` is due. Returns without waiting for sessions. |
| `release ID [--note T]` | Drop a claim now: collect it if a result is waiting, otherwise keep partial work and requeue, without a cooldown. |
| `retry ID [--note T] [--tier T]` | Send blocked or failed work back to `ready/` with attempts reset, optionally to another tier (for example `judgement` when lighter agents keep failing it). Operator steps (`kind: human`) are closed with `resolve --done` instead; `resolve --requeue` on them only adds the note. |
| `pause`, `resume` | Stop or restart taking new work; ticks still collect finished results. |
| `add FILE` | Enqueue a hand-written fragment (`kind: human` goes to `human/`). |
| `cooldown --agent A [--until ISO\|--clear]` | Show, set or clear a cooldown. |

Human fragments notify once, when their deps are done, not when they are
created.

Reviews block only on the fragment's own Goal and Acceptance, regressions,
or contradictions with its Read first documents. New requirements and
problems in unchanged code go under `Follow-ups` and never change the
verdict; the operator turns them into fragments with `add`.

## Launching agents

loopq is not tied to any harness. Per agent, the config may set:

```yaml
agents:
  claude-pro:
    model: "model-id-from-your-harness"
    command: ["claude", "-p", "{prompt}"]      # argv or a string; {prompt} {worktree} {id} {model}
    transcripts: "~/.claude/projects/-Users-al-work-wt-claude/*.jsonl"   # optional; ** recurses
```

`model` is shown by `tick --manual`. To pass it to a CLI runner, include
`{model}` with the CLI's verified model option in `command`. External harness
automations choose their model in their own settings.

- Use one cron entry for every loop and agent. Put each loop config in one
  directory, then run `loopq dispatch --config-dir DIR` each minute. An agent
  with `command` starts a local runner. An agent with `launcher: orca` and
  `cron` triggers its matching Orca automation, whose own schedule must be
  disabled. The dispatcher returns without waiting for sessions.
- The local runner saves complete agent output and sets `LOOPQ_FRAGMENT` and
  `LOOPQ_AGENT` in its environment.
- A scheduler that launches the harness itself (for example an Orca
  automation) runs `loopq tick --agent <name>` as its precheck. `session`
  then reads the files matching `transcripts` that changed during the claim.

Preview what the dispatcher will start:

```sh
loopq dispatch --dry-run
```

One cron entry handles all configs in the default directory:

```cron
* * * * * /absolute/path/to/loopq dispatch >>/absolute/path/dispatch.log 2>&1
```

Use absolute paths and make sure cron's `PATH` includes `uv`, `git` and
`orca` when needed. Agents without `command` or `launcher: orca` remain manual. See the
[dispatcher details](docs/configuration.md#one-cron-job-for-all-loops).

## Tests

```sh
uv run --with pytest==9.1.1 --with pyyaml==6.0.3 --with rich==15.0.0 pytest -q
```

Tests drive only the command line against a temporary repository, worktrees
and queue.
