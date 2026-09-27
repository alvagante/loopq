# Command reference

Run `loopq help` or `loopq -h` for the CLI overview, and
`loopq help COMMAND` or `loopq COMMAND -h` for options. Bare `loopq` runs
`doctor`.

## Selecting a loop

loopq discovers `.yaml` and `.yml` configs in `~/.config/loopq/loops.d/`.
`loopq loops` lists their project names and paths. With one config, selection
is optional. With multiple configs:

- `doctor`, `status`, `todo`, `milestones`, and read-only `cooldown` show all loops.
- `runs` combines sessions across loops, with one `--limit` for the combined list.
- `show`, `history`, and `session` find a unique fragment ID across loops.
- `why` and state-changing commands except `dispatch` require `--loop PROJECT` or `--config FILE`.
- `dispatch` always scans every config in its config directory.

Use `--loop PROJECT` to select one discovered project. Use `--config FILE` or
`LOOPQ_CONFIG=FILE` to select an explicit config. Use `--config-dir DIR` or
`LOOPQ_CONFIG_DIR=DIR` to change the discovery directory. The queue lives in
`$LOOPQ_HOME/<project>/` (default `~/.loops`).

## Operator tasks

| Command | Purpose |
| --- | --- |
| `doctor` | Show blockers first, then human items and briefs needing attention. Exit 1 when action is needed. |
| `todo` | Show actionable human steps, steps waiting on dependencies, and unread briefs. |
| `resolve ID --done [--note TEXT]` | Complete a human fragment. |
| `resolve ID --requeue [--note TEXT]` | Return a blocked fragment to agents. For a `kind: human` step, record the note and leave it with the operator. |
| `ack MILESTONE` | Mark a milestone brief read and release its hold. |

## Inspect

| Command | Purpose |
| --- | --- |
| `help [COMMAND]` | Show the overview or detailed help for one command. |
| `loops` | List discovered projects and config paths. |
| `status` | Show queue counts, claims, human items, cooldowns, and unread briefs. |
| `milestones` | Show progress and dependencies for each milestone. |
| `show ID` | Show a fragment, dependency states, commits, and history. |
| `history ID` | Show every recorded transition of a fragment. |
| `why AGENT` | Explain why an agent took no work, including eligibility of ready fragments. |
| `runs [--agent NAME] [--failed] [--limit N]` | List agent sessions and outcomes. Default limit: 30. |
| `session ID [--paths]` | Show captured run output or matching harness transcripts; `--paths` lists transcript paths. |

## Run the loop

| Command | Purpose |
| --- | --- |
| `add FILE` | Enqueue a Markdown fragment. `kind: human` enters the human queue. |
| `tick --agent NAME [--manual]` | Collect this agent's result, then reserve its next fragment. `--manual` prints the worktree and prompt. Exit 0 means work reserved, 1 means none, 2 means refused. |
| `run --agent NAME` | Tick, launch the agent's configured `command` in its worktree, capture output under `logs/runs/`, and collect the result. A failed run without a result keeps partial work, requeues the fragment, and cools down the agent. |
| `dispatch [--dry-run]` | Check schedules across all configs and launch command agents or matching Orca automations. Return without waiting for sessions. `--dry-run` previews due actions. |
| `release ID [--note TEXT]` | Release a claim now. Collect an available result, or keep partial work and requeue without a cooldown. |
| `handoff ID [--to AGENT] [--note TEXT]` | Move a claim from an agent stuck on usage limits. Stop its `loopq run` session, keep partial work on the fragment branch, cool the agent down, and requeue the fragment for `--to AGENT` only (default: any eligible agent). A finished result is collected instead. Without a claim, `--to` redirects a ready fragment. |
| `retry ID [--note TEXT] [--tier TIER]` | Return blocked or failed work to the ready queue with attempts reset. Tier choices: `judgement`, `standard`, `mechanical`. Close operator steps with `resolve --done`. |
| `pause` | Stop new claims while still collecting finished results. |
| `resume` | Allow new claims again. |
| `cooldown [--agent NAME [--until ISO\|--clear]]` | Without `--agent`, show every agent as cooling down or available. With it, show, set, or clear that agent's cooldown. |

`run` exits 1 without launching if a previous run for that agent is alive.
When a launched command finishes, `run` returns its exit code. Human fragments
notify once when their dependencies are done.

`handoff` stops only sessions started by `run` or `dispatch`; stop an Orca or
`tick --manual` session yourself. The target takes the fragment on its next
`run`, `tick`, or scheduled dispatch; `retry` removes the assignment.

Reviews block only on the fragment's Goal and Acceptance, regressions, or
contradictions with its Read first documents. New requirements and problems in
unchanged code go under `Follow-ups`; the operator can enqueue them with `add`.

Terminal output uses color and tables; piped output is plain text at 220
columns or the width set by `COLUMNS`. `NO_COLOR` and `FORCE_COLOR` are honored.
See [configuration](configuration.md) for agent commands, transcripts, gates,
and scheduling.
