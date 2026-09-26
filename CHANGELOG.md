# Changelog

Notable user-visible changes are recorded here.

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
