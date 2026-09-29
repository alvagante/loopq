# Set up or reconfigure a loop

Work from the target project's Git checkout. Read the installed loopq checkout's
`docs/quickstart.md` and `docs/configuration.md` for current setup and YAML
fields, and use `loopq help COMMAND` for flags. If loopq is absent, locate its
checkout or public docs before planning installation. If neither is available,
propose cloning `https://github.com/alvagante/loopq.git` to an unused path.
Inspect `manage.sh` before installing. loopq requires Git, uv, and Python 3.11
or newer.

## Discover

Inspect the current branch, HEAD, Git status and worktrees, existing loopq
configs, `LOOPQ_CONFIG_DIR` and `LOOPQ_HOME`, installed commands, and available
agent harnesses. Check whether another loop uses this repository and whether
the delivery branch moves independently. Inspect `loopq loops` when the CLI
is installed. Keep discovery read-only; verify with `loopq doctor` after
applying the approved setup.

Ask for choices that inspection cannot settle: starting commit, delivery branch,
agent identities and roles, available harnesses and models, accepted tiers and
kinds, and manual versus command or external launches. Review needs a second
agent identity. Ask whether scheduling is wanted; if so, collect cadence, time
zone, and launcher. Bundle the unresolved choices into one message.

## Propose

Show the exact start ref and commit because uncommitted edits are excluded.
Propose a distinct local base branch, one detached worktree per agent identity,
an integration worktree, and their absolute paths and Git commands. Keep the
base branch unchecked out. Show the config path and complete YAML for a guided
setup; place it in `LOOPQ_CONFIG_DIR` (default
`~/.config/loopq/loops.d/`), outside agent worktrees. Include a distinct
`project` and `prefix`, `base`, `integration_worktree`, gate, and each agent's
worktree, model, tiers, and kinds. For reconfiguration, show the current and
proposed values and preserve existing paths and state.

For a starter scaffold, explain that `loopq create` writes YAML and prints Git
commands but does not create a branch or worktree. Show its target path and
get approval before running it. Review the generated YAML and commands with
the operator before creating Git state or adding a scheduler.

Verify each headless harness command against its own CLI help. A command gets
no standard input, so pass every choice as an argument. `model` reaches a
command runner only through `{model}`; an external automation selects its own
model. Use `docs/configuration.md` for launcher-specific details. Show the
effect of each proposed command. The current checkout stays on its branch;
loopq advances its base, and the operator later merges that base into the
delivery branch.

Get explicit approval for the exact installation, config, branch, and worktree
changes before applying them. Reuse a valid existing setup and preserve
conflicting paths for the operator to decide. If the plan changes materially,
show the revision before applying it.

## Schedule only when requested

If loopq controls scheduling, use one host cron entry for `loopq dispatch`
and keep per-agent schedules in YAML. If a harness scheduler stays in control,
use `loopq tick --agent NAME --config FILE` as its precheck. Avoid duplicate
triggers. Show the proposed cron line, affected entries, log path, PATH
requirements, and automation changes. Get separate approval before changing
cron or an external scheduler.

## Apply and verify

After approval, apply the reviewed changes. For a new loopq checkout, preview
`manage.sh install --dry-run --no-skill`, then install the CLI at an unused
path on `PATH` with `manage.sh install --no-skill`. The current harness already
has this skill. Use `--skill` only if the operator asks to link it into other
harnesses globally. If Git, uv, or Python must be installed, include the
package-manager step in the approved plan.

Verify the resulting setup with `loopq loops` and
`loopq doctor --loop PROJECT`. Save a default with `loopq use PROJECT` only
when requested. For scheduled setups, also inspect the installed scheduler
and run `loopq dispatch --dry-run`. Report the installed path, branch,
worktrees, config, queue path, agent roles and models, schedule, verification
results, and the next command to add work. Enqueue or launch work only when
requested.
