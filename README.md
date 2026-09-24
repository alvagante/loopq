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
`$LOOPQ_HOME/<project>/` (default `~/.loops`).

| Command | Purpose |
|---|---|
| `tick --agent A [--manual]` | Collect A's finished fragment, then reserve the next one. Exit 0 = work reserved (the Orca precheck runs the agent), 1 = nothing, 2 = refused. |
| `add FILE` | Enqueue a hand-written fragment. |
| `status` | Counts, claims, human items, cooldowns, unread briefs. |
| `resolve ID --done\|--requeue [--note T]` | Close or return a human fragment. |
| `cooldown --agent A [--until ISO\|--clear]` | Show, set or clear a cooldown. |
| `ack MILESTONE` | Mark a brief read and release a `hold`. |

Not implemented yet: `run` (the `launchd` launcher for harnesses Orca cannot
drive).

## Tests

```sh
uv run --with pytest==9.1.1 --with pyyaml==6.0.3 pytest -q
```

Tests drive only the command line against a temporary repository, worktrees
and queue.
