# Act on a loop

Confirm the loop with `loopq loops` and `--loop PROJECT`, then confirm the
fragment or agent ID before mutating. Prefer a short plan and approval when
the change is hard to reverse (prune, handoff away from a live session,
clearing cooldown early).

## Operator decisions

| Situation | Command |
| --- | --- |
| Human fragment finished | `loopq resolve ID --done [--note TEXT]` |
| Return blocked work to agents | `loopq resolve ID --requeue [--note TEXT]` |
| Unread milestone brief | `loopq ack MILESTONE` |
| Blocked or failed work should retry | `loopq retry ID [--note TEXT] [--tier TIER]` |

Close operator steps with `resolve --done`. Use `retry` for agent work that
should re-enter `ready` with attempts reset.

## Claims and agents

| Situation | Command |
| --- | --- |
| Release a claim now | `loopq release ID [--note TEXT]` |
| Agent stuck on usage limits | `loopq handoff ID [--to AGENT] [--note TEXT]` |
| Show or set cooldown | `loopq cooldown` / `loopq cooldown --agent NAME ...` |
| Stop new claims | `loopq pause` |
| Allow claims again | `loopq resume` |

`handoff` stops sessions started by `run` or `dispatch` only; stop an Orca or
`tick --manual` session yourself. Without a claim, `--to` redirects a ready
fragment.

## Housekeeping

Preview archival with `loopq prune --dry-run`, then prune only after approval.
Default age is 30 days. Report what changed and what still needs attention
(`loopq doctor` or `loopq todo`).
