# Enqueue work

Orient with `loopq loops` and confirm which loop will receive the fragment.
Use `--loop PROJECT` for the enqueue; save a default with `loopq use PROJECT`
only when requested.

## Write a fragment

Prefer `loopq new PATH --title TEXT --tier TIER` for a work template, or
`--kind human` for an operator step. Edit the template outside agent
worktrees. Fill Goal, Read first, Files, and Acceptance so another agent can
execute without guessing. Keep one job per fragment.

Valid work tiers are `judgement`, `standard`, and `mechanical`. Choose the
narrowest tier that matches the judgment required. Add `--milestone ID` or
`--deps ID,ID` when the user names them.

## Enqueue

Run `loopq add FILE`. Confirm with `loopq list --state ready` (or
`--kind human` for operator steps). Report the fragment ID and the next
command to start an agent (`tick` / `run`) only if the user asked to launch.

Check `loopq status --loop PROJECT` when unsure whether the loop is paused.
Tell the user before enqueueing into a paused loop. Derive Goal and Acceptance
from the requested outcome and repo evidence; ask when missing criteria would
change the work.
