# Monitor a loop

Start with `loopq loops`, then use `--loop PROJECT` to scope a view. Save a
default with `loopq use PROJECT` only when requested. `LOOPQ_LOOP` and the
current worktree can also select a loop. Use `--all` for a combined view.

## What needs attention

| Need | Command |
| --- | --- |
| Blockers and human items | `loopq doctor` (exit 1 when action is needed) |
| Actionable human steps and unread briefs | `loopq todo` |
| Queue counts, claims, cooldowns | `loopq status` |
| Milestone progress | `loopq milestones` |

## Inspect work and agents

| Need | Command |
| --- | --- |
| List fragments | `loopq list` with `--state`, `--kind`, `--tier`, `--agent` as needed |
| One fragment | `loopq show ID` or `loopq history ID` |
| Why an agent took nothing | `loopq why AGENT` |
| Recent sessions | `loopq runs` / `loopq runs --failed` |
| Captured output | `loopq session ID` |
| Throughput | `loopq stats` |

Report findings in priority order: blockers, human items, failed runs, then
idle agents. Propose the matching action from [act.md](act.md) or
[run.md](run.md) only when the user wants you to change state. Prefer
`loopq help COMMAND` for options.
