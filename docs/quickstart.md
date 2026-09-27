# Quickstart

To have your agent do these setup steps, use the
[loopq-setup skill](../skills/loopq-setup/SKILL.md). Continue at
[Add work](#3-add-work) after it verifies the loop.

This example runs two agent identities with your existing agent harness against
an existing Git repository. The harness can be Codex, Claude Code, or another
tool that can work in a chosen directory. loopq does not install anything into
the harness: it prepares a worktree and a task file, then collects a result
file. Use a clean project checkout. Run the Git setup commands from that
project's root, not from the loopq checkout.

## 1. Create a base branch and worktrees

```sh
git branch loop-base
git worktree add --detach ../project-loop-author loop-base
git worktree add --detach ../project-loop-reviewer loop-base
git worktree add --detach ../project-loop-integration loop-base
```

Replace `project` in the worktree paths with a suitable name. The `loop-base`
branch must stay unchecked out: loopq moves it after review. The integration
worktree is for loopq, not an agent. Each agent needs its own worktree. The
original checkout can stay on its current branch.

## 2. Register the project loop

Create the config directory:

```sh
mkdir -p ~/.config/loopq/loops.d
```

Save this as `~/.config/loopq/loops.d/example.yaml`. Replace each
`/absolute/path` with the path from step 1. `project` names the queue
directory, so use a distinct name for each project. The config stays outside
the agent worktrees because loopq requires them to be clean before assigning
work.

```yaml
project: example
prefix: ex
base: loop-base
integration_worktree: /absolute/path/project-loop-integration
lease: 4h
gate:
  - git diff {base}...HEAD --check
agents:
  author:
    worktree: /absolute/path/project-loop-author
    tiers: [judgement, standard, mechanical]
    kinds: [work, review, conflict, decompose, brief]
  reviewer:
    worktree: /absolute/path/project-loop-reviewer
    tiers: [judgement, standard, mechanical]
    kinds: [work, review, conflict, decompose, brief]
```

```sh
loopq loops
loopq use example
loopq doctor
```

`loopq use example` saves `example` as the default loop, so the later
commands can omit `--loop example`. `--loop PROJECT`, `LOOPQ_LOOP`, or
running inside a loop worktree select a loop too; see the
[command reference](commands.md#selecting-a-loop).

The queue is created at `~/.loops/example/` by default. Set `LOOPQ_HOME` to
another parent directory if needed. If you prefer to keep the config elsewhere,
symlink it into `loops.d` instead.

## 3. Add work

Save this as `first-fragment.md` outside the worktrees:

```markdown
---
title: Write a greeting
kind: work
tier: standard
deps: []
---
## Goal
Create hello-loopq.txt with the single line hello.

## Read first
README.md

## Files
hello-loopq.txt

## Acceptance
test "$(cat hello-loopq.txt)" = hello
```

```sh
loopq add first-fragment.md
loopq status
loopq tick --agent author --manual
```

The tick prints the author's worktree path and this prompt:

```text
Read .loop/FRAGMENT.md in this worktree and follow it exactly.
```

Start a fresh session in your harness with that worktree as its working
directory, then send the prompt. The task file includes the fragment, agent
instructions and the required `.loop/RESULT.md` format. The agent should not
commit or push. If the harness cannot choose a working directory, start it
from that worktree in a terminal. Keep the author and reviewer identities in
their respective worktrees, even if both use the same harness.

When the author finishes, collect its result and assign the review:

```sh
loopq tick --agent author
loopq tick --agent reviewer --manual
```

Start a separate reviewer session in its printed worktree with the same
prompt. After it writes its result, collect and integrate:

```sh
loopq tick --agent reviewer
loopq show ex-0001
loopq doctor
```

Each tick first collects the prior result, then tries to claim another
fragment. Exit 0 means a new task was claimed, so launch that agent again;
exit 1 means nothing was assigned (check `loopq doctor` or `loopq why author`
for the reason). Exit 2 means the tick was
refused. An approved review moves
`loop-base`, not your original branch. Merge or cherry-pick from `loop-base`
into your normal branch when you decide to adopt the work.

For unattended sessions, set `agents.NAME.command` to a harness CLI invocation
that accepts the `{prompt}` argument, then run
`loopq run --agent author` or let the single cron dispatcher
schedule it. `run` calls `tick` itself. If the harness owns scheduling, make
`loopq tick --agent NAME` its precheck and launch the session
only on exit 0. See the
[configuration reference](configuration.md#one-cron-job-for-all-loops) for
dispatch and Orca setup.
