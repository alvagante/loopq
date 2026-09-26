# loopq

A local fragment queue that lets several agent budgets (Claude Code, Codex,
Cursor, opencode, ...) pull session-sized work from one plan, semi
unattended. Claims, gates, cross-agent review, integration, lease expiry and
cooldowns are plain script; agents only read `.loop/FRAGMENT.md` and write
`.loop/RESULT.md` in their own worktree.

The contract is the fragment loop spec (first used in openskills.info at
`docs/loops/workflows/fragment-loop.md`).

## Install

Needs `uv` and git. The script carries its dependency (PEP 723).

```sh
ln -s ~/Documents/GITHUB/loopq/loopq.py ~/.local/bin/loopq
```

## Commands

All take `--config <loop.yaml>` (or `LOOPQ_CONFIG`). The queue lives in
`$LOOPQ_HOME/<project>/` (default `~/.loops`). Bare `loopq` runs `doctor`.

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
    command: ["claude", "-p", "{prompt}"]      # argv or a string; {prompt} {worktree} {id}
    transcripts: "~/.claude/projects/-Users-al-work-wt-claude/*.jsonl"   # optional; ** recurses
```

- With `command`, schedule `loopq run --agent <name>` from anything (cron,
  a `launchd` `StartInterval` job, a shell loop). The run log is complete
  output, and the agent's environment carries `LOOPQ_FRAGMENT` and
  `LOOPQ_AGENT`.
- A scheduler that launches the harness itself (for example an Orca
  automation) runs `loopq tick --agent <name>` as its precheck. `session`
  then reads the files matching `transcripts` that changed during the claim.

For example, every 20 minutes from cron:

```cron
*/20 * * * * LOOPQ_CONFIG=/path/loop.yaml loopq run --agent codex >/dev/null 2>&1
```

## Tests

```sh
uv run --with pytest==9.1.1 --with pyyaml==6.0.3 --with rich==15.0.0 pytest -q
```

Tests drive only the command line against a temporary repository, worktrees
and queue.
