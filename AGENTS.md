# Working on loopq

loopq is a local CLI for coordinating coding agents in separate Git worktrees.
The implementation is one Python script, `loopq.py`, with inline uv dependencies.
`manage.sh` installs a symlink to that script. The user workflow is in
`README.md`; configuration details are in `docs/configuration.md`.

## Code map

- `Queue` and `Fragment` manage queue files and events under `LOOPQ_HOME`.
- Selection, worktree preparation, collection, review, gates, and integration
  are in `loopq.py`. Follow that flow before changing queue behavior.
- `dispatch` scans configs in `LOOPQ_CONFIG_DIR` and schedules command or Orca
  agents. Keep its single cron entry model when changing scheduling.
- `skills/loopq-setup/SKILL.md` guides installation and project setup.

## Changes and verification

- Keep CLI options, help text, README, configuration docs, and the setup skill
  consistent when a user-facing behavior changes.
- Use the CLI tests in `tests/` with temporary repositories and worktrees for
  queue, Git, and dispatcher changes.
- Run `uv run --with pytest==9.1.1 --with pyyaml==6.0.3 --with rich==15.0.0 pytest -q`
  for behavioral changes. Run `git diff --check` for all changes.
- Keep live queues, worktrees, agent automations, and cron outside test work;
  change them only when the task calls for it.
