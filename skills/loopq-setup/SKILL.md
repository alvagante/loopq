---
name: loopq-setup
description: Set up or reconfigure loopq for an existing Git project, including agent roles, models, worktrees, YAML config, and optional scheduling.
---

# Set up a loopq project

Work from the project's Git checkout. Complete the setup yourself after the
user approves the concrete changes. Read the installed loopq checkout's
`docs/quickstart.md` and `docs/configuration.md` when available. If loopq is
not installed, read the public repository docs or an existing checkout first.
If neither is available, propose cloning
`https://github.com/alvagante/loopq.git` to an unused directory and get
approval before creating it. If the repository is not public, ask for a local
checkout path. Read its docs and `manage.sh` before installing. loopq requires
Git, uv, and Python 3.11 or newer.

## Discover and ask

Inspect the current branch and HEAD, Git status and worktrees, existing loopq
configs, `LOOPQ_CONFIG_DIR` and `LOOPQ_HOME`, installed commands, and available
agent harnesses. Check whether other loops use this Git repository and whether
`main` or another delivery branch is moving independently. Keep discovery
read-only.

Ask the user for the roles they want, the model and harness available for each
role, and whether each agent runs manually, through a headless command, or
through an existing automation. Ask which roles may write, review, decompose,
or handle briefs, and which tiers they should accept. Explain that review
needs a second agent identity and an author cannot review its own work. Ask
whether scheduling is wanted; if so, collect cadence, time zone, and launcher
preference. Clarify the starting commit when the checkout is dirty or the
intended base is unclear. Ask which branch should eventually receive the
loop's results. Bundle these questions into one concise message.

## Propose the setup

Show a reviewable plan with the exact installation steps if needed, local base
branch, one detached worktree per agent identity, one integration worktree,
their absolute paths, and the Git commands. Keep the base branch unchecked
out. Name the base and worktrees distinctly from any other loop in this
repository. Show the selected start ref explicitly, since uncommitted edits
are not included. Explain that the user's current checkout and branch stay
in place, the loop advances its base after review, and the user merges that
base into a delivery branch when ready. Reuse a valid existing setup and
preserve conflicting paths for the user to decide.

Show the full proposed YAML before writing it. Put it in `LOOPQ_CONFIG_DIR`
(default `~/.config/loopq/loops.d/`), outside agent worktrees. Include a
distinct `project` and `prefix`, `base`, `integration_worktree`, a suitable
gate, and each agent's `worktree`, `model`, `tiers`, and `kinds`. Valid tiers are
`judgement`, `standard`, and `mechanical`; common kinds are `work`, `review`,
`conflict`, `decompose`, and `brief`. The `model` field is shown by
`tick --manual`; command runners receive it only when their `command` uses
`{model}`. Verify the harness's CLI syntax before adding a `command`. An
external automation selects its model in that harness, not through loopq.
A command runs without standard input, so it must pass every choice as an
argument. When a harness prompts for a model at startup, as OpenCode does
under `ollama launch` (and so under Orca), use `command` with `{model}`
rather than an Orca automation; see the configuration reference.

Explain the effect of the proposed commands and config. Get explicit approval
for installation and Git workspace creation, and approval of the exact YAML
before writing or changing it. If approval was already given for that exact
plan in the conversation, use it. If the plan changes materially, show the
revision before applying it. Do not overwrite an existing executable,
worktree, branch, or config. Include a trusted package manager method in the
proposal if uv or Python must be installed. Do not use pipe-to-shell
installation.

## Scheduling, only when requested

If loopq controls scheduling, use one host cron entry running `loopq dispatch`
for all discovered loops and put each agent's five-field `cron` schedule in
its YAML. A local command agent needs a verified `command`; an Orca agent
needs `launcher: orca` and a matching existing automation whose precheck
selects this config and agent. Disable that automation's own schedule when
dispatcher scheduling takes over. If an existing harness scheduler remains
in control, use `loopq tick --agent NAME --config FILE` as its precheck and do
not add a second cron trigger. Preserve unrelated crontab entries and avoid
duplicate schedules. Show the proposed cron line if any, affected existing
entries, log path, PATH requirements, and automation changes. Ask separately
for approval before changing cron or an external scheduler.

## Execute and verify

After approval, run the setup commands. For a new loopq checkout, preview
`manage.sh install --dry-run`, then install to an unused bin path on `PATH`.
Verify with `loopq loops` and `loopq doctor --loop PROJECT`. Optionally run
`loopq use PROJECT` to save the new loop as the default for later commands.
For scheduled
setups driven by loopq, also run `loopq dispatch --dry-run` and inspect the
installed cron entry. Report the installed path, branch, worktrees, config,
queue path, roles and models, schedule if any, verification results, and the
next command to add a fragment. Enqueue or launch work only if the user
requested it.
