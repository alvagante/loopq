# Changelog

Notable user-visible changes are recorded here.

## [0.3.0] - 2026-09-29

### Added

- `version` prints the loopq version without requiring a loop config.
- Docker image and release workflow for versioned GHCR and Docker Hub images.
- `create` writes a starter loop config and prints the branch and worktree
  commands needed to finish setup.
- `new` writes a work or human fragment template for `add`.
- `list` filters fragments by state, kind, tier, milestone or agent, with JSON
  output; `runs` also supports JSON output.
- `stats` reports cycle times and agent throughput.
- `prune` archives completed fragments after an age threshold, with a dry-run
  preview.

### Fixed

- `loopq use --all` now clears the saved loop so later views cover all loops
  when no environment or directory selector takes precedence.

### Documentation

- Expanded setup and parallel worktree guidance, Docker usage, and common
  operator commands in the README and references.

## [0.2.0] - 2026-09-28

### Added

- `handoff ID [--to AGENT] [--note TEXT]` moves a claim away from an agent
  stuck on usage limits. It stops the agent's `run` session, keeps partial
  work on the fragment branch, cools the agent down and requeues the fragment,
  optionally for one named agent.
- `cooldown` without `--agent` shows the status of every agent.
- Command reference in `docs/commands.md` and a recorded demo in the README.
- `use [NAME | --clear]` shows, saves or clears the default loop. Without
  `--loop`, `--config` or `LOOPQ_CONFIG`, loopq now picks a default loop from
  `LOOPQ_LOOP`, the current worktree or repository, then the name saved by
  `loopq use NAME`; a default acts like `--loop` and is reported on standard
  error, and `--all` ignores it for one command.

### Changed

- The license is now Apache License 2.0 (was MIT).

### Fixed

- `run` starts the agent with no standard input, so a harness that prompts at
  startup (such as the Ollama model picker for OpenCode) fails and requeues
  instead of holding its claim until the lease ends.
- A `run` session that exits after its fragment was handed to another agent no
  longer expires that agent's claim.

### Documentation

- Model selection for harnesses that prompt at startup, with an OpenCode
  through Ollama example, and why an Orca automation cannot pass a model.

## [0.1.0] - 2026-09-26

### Added

- Local fragment queue with dependencies, human steps, milestone holds, agent
  claims and leases.
- Git worktree workflow with result collection, independent review, integration
  gates, retry and cooldown handling.
- Manual agent ticks, local command runner and one cron dispatcher for multiple
  loops and agents, including Orca automations.
- Per-agent model identifiers for manual handoff and command templates.
- Config discovery from `loops.d`, loop selection by project name, and combined
  views for status, operator work, milestones and agent runs.
- Fragment history, session output, diagnostic commands and command-specific help.
- Install and uninstall helper, setup skill, quickstart, configuration
  reference, MIT license and automated tests.
