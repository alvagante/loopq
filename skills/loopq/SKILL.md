---
name: loopq
description: >-
  Create or reconfigure a loopq project; enqueue work; check status or diagnose
  a loop; unblock, pause, or hand off; run or schedule ticks.
---

# loopq

Coordinate coding agents through loopq: a local CLI that assigns fragments,
reviews them with a second agent identity, and integrates approved work onto a
dedicated base branch. Work from the project's Git checkout unless the task is
installing loopq itself.

Read one disclosed file for the job, then follow it. Prefer `loopq help COMMAND`
for flags and the installed checkout's `docs/configuration.md` for YAML fields.
Do not invent CLI options.

## Choose a path

| Job | Read |
| --- | --- |
| Install loopq; create or reconfigure a loop, worktrees, YAML, or scheduler | [setup.md](setup.md) |
| Write or enqueue fragments, goals, acceptance, tiers | [work.md](work.md) |
| List loops, status, doctor, todo, milestones, runs, why | [monitor.md](monitor.md) |
| Resolve, ack, retry, handoff, cooldown, pause, resume, prune | [act.md](act.md) |
| Tick an agent, run a session, or preview or trigger dispatch | [run.md](run.md) |

If the request spans jobs, finish the first needed path before opening the next.

## Hard rules

- Get explicit approval before installing binaries, creating or removing Git
  worktrees or branches, writing loop YAML, or changing cron or an external
  scheduler.
- Do not overwrite an existing executable, worktree, branch, or config.
- Do not use pipe-to-shell installation.
- Review needs a second agent identity; an author cannot review its own work.
- Use `loopq loops` and `loopq doctor --loop PROJECT` to orient before
  mutating a live loop. Save a default with `loopq use PROJECT` only when
  requested.
