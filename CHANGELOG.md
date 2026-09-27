# Changelog

Notable user-visible changes are recorded here.

## [0.2.0] - 2026-09-26

### Added

- `handoff ID [--to AGENT] [--note TEXT]` moves a claim away from an agent
  stuck on usage limits. It stops the agent's `run` session, keeps partial
  work on the fragment branch, cools the agent down and requeues the fragment,
  optionally for one named agent.
- `cooldown` without `--agent` shows the status of every agent.
- Command reference in `docs/commands.md` and a recorded demo in the README.

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
