# Run or schedule the loop

Confirm the loop and agent name first. Agents work in their configured
worktrees; do not launch from the user's delivery branch checkout.

## Manual cycle

Use when the user runs the harness themselves:

1. `loopq tick --agent NAME --manual` prints the worktree and prompt.
2. Run the agent there; it reads `.loop/FRAGMENT.md` and writes
   `.loop/RESULT.md`.
3. `loopq tick --agent NAME` collects the result and may reserve the next
   fragment.
4. Repeat for the reviewer identity after the author finishes.

Exit codes for `tick`: 0 work reserved, 1 none, 2 refused. Use
`loopq why AGENT` when nothing is reserved.

## Headless `run`

`loopq run --agent NAME` ticks, launches the agent's configured `command` in
its worktree, captures output under `logs/runs/`, and collects the result. It
exits 1 without launching if a previous run for that agent is still alive. A
failed run without a result keeps partial work, requeues the fragment, and
cools down the agent.

Verify the `command` in the YAML before relying on `run`. See
[setup.md](setup.md) when the command or model substitution is wrong.

## Dispatch

`loopq dispatch` scans every config and launches due command agents or
matching Orca automations without waiting. Preview with
`loopq dispatch --dry-run`.

For installing or changing cron, per-agent schedules, or an external
scheduler, follow [setup.md](setup.md). Confirm that one scheduler controls
each agent before triggering dispatch.
