# Configuration

loopq discovers `.yaml` and `.yml` configs in `~/.config/loopq/loops.d/`.
Use `loopq loops` to list them and `--loop PROJECT` to select a project by the
config's `project` field. If there is only one config, selection is optional.
Bare `loopq` runs `doctor` across every discovered loop. `status`, `todo`,
`milestones`, and read-only `cooldown` show each loop. `runs`
combines sessions across loops with a global `--limit` (30 by default).
`show`, `history`, and `session` find a unique fragment ID across loops.
`why` requires a loop when multiple are discovered because its output can be
long. Other commands that change state require `--loop PROJECT` when multiple
loops exist, unless a default loop is set with `LOOPQ_LOOP`, the current
worktree, or `loopq use PROJECT`; a default also narrows the views to that
loop (see [commands](commands.md#selecting-a-loop)). `dispatch` always scans
every loop. Pass `--config FILE` or set
`LOOPQ_CONFIG=FILE` to use an explicit file. `LOOPQ_CONFIG_DIR` or
`--config-dir DIR` changes the discovery directory.

The [quickstart](quickstart.md) contains a complete manual example.
Run `loopq create` from a Git checkout to write a starter config at
`LOOPQ_CONFIG_DIR/PROJECT.yaml` (default `~/.config/loopq/loops.d/PROJECT.yaml`).
Use `--project NAME` or pass a config path to override those defaults. The
command detects Claude Code, Codex, Cursor Agent, OpenCode, Gemini CLI,
GitHub Copilot CLI, Kiro CLI, Goose, Amp, Droid, Crush, Qwen, and Pi binaries
on `PATH`. It adds documented headless commands where available and leaves
other detected agents manual. If none are found,
it adds manual `author` and `reviewer` entries. Review the generated commands,
model choices, agent roles, gate and paths. Create the base branch and detached
worktrees before running the loop. The generated base is
`loop-PROJECT-base`, which avoids a shared branch name when several loops use
one repository. Its prefix starts as the project name; shorten it if useful,
but keep prefixes distinct across loops so fragment IDs are unambiguous.
The config generator prints setup commands but does not run
them. Choose their `START_REF` deliberately: `main` uses its current local
commit, while `HEAD` uses the current checkout's commit. Working tree edits
are not part of either ref.

| Key | Meaning |
|---|---|
| `project` | Queue directory name under `LOOPQ_HOME` (default `~/.loops`). |
| `prefix` | Generated fragment ID prefix, for example `ex-0001`. |
| `base` | Local branch loopq integrates approved work into; leave it unchecked out. It does not track `main` automatically. |
| `integration_worktree` | Dedicated Git worktree for integration. |
| `agents.NAME.worktree` | Dedicated Git worktree for this agent. |
| `agents.NAME.model` | Optional model identifier. `tick --manual` prints it, and `{model}` in `command` expands to it. External harnesses must select the model themselves. |
| `agents.NAME.tiers` | Accepted tiers: `judgement`, `standard`, `mechanical`. |
| `agents.NAME.kinds` | Accepted kinds: `work`, `review`, `conflict`, `decompose`, `brief`. |
| `lease` | Claim duration such as `4h`; default `4h`. |

At least two agent identities are needed for cross-agent review. An agent
cannot review work it authored. loopq does not create worktrees or check your
base branch out for you. Agent worktrees must be clean when taking work.
Your normal checkout may stay on `main` or a feature branch. To bring loop
results into that branch, merge the base yourself. See
[the parallel work example](../README.md#work-alongside-other-branches) and
[the sync procedure](quickstart.md#keeping-the-loop-current).

Optional settings:

| Key | Meaning |
|---|---|
| `agents.NAME.command` | Command run by `loopq run`; argv list or shell-style string. `{prompt}`, `{worktree}`, `{id}` and `{model}` are substituted in each argument. Using `{model}` requires `agents.NAME.model`. |
| `agents.NAME.transcripts` | Optional glob for transcripts used by `loopq session` when another launcher runs the agent. |
| `agents.NAME.limit_cooldown` | Cooldown after a parked, failed, or handed-off session, for example `2h`. |
| `agents.NAME.cron` | Optional five-field numeric cron schedule, interpreted in the cron host's local time by `dispatch`. |
| `agents.NAME.launcher: orca` | Trigger an existing Orca automation through the Orca CLI when `cron` is due. Its precheck must call `loopq tick` for this agent and config. |
| `gate` | List of shell commands run in the worktree after work and before integration. Nonzero exit blocks progress. `{base}` is substituted. |
| `forbid_chars` | Characters rejected in added diff lines by the gate. |
| `notify` | Command argv called for human steps and briefs; the message is appended as its last argument. |
| `preamble` | Text prepended to each agent's `.loop/FRAGMENT.md`. |
| `templates` | Overrides for built-in instructions by fragment kind. |
| `milestones` | Ordered list of `{id, source, after, hold}` records. loopq creates decomposition and brief fragments as milestones progress. |
| `brief_followup` | Optional `{title, tier, goal}` work fragment created after a brief. |

For example, an agent launcher can be configured as:

```yaml
agents:
  codex:
    worktree: /absolute/path/project-loop-codex
    tiers: [judgement, standard, mechanical]
    kinds: [work, review, conflict, decompose, brief]
    command: ["codex", "exec", "{prompt}"]
```

Check the agent's own CLI syntax before using a launcher. `loopq run` starts
the configured command in its worktree, saves stdout and stderr under the
queue's `logs/runs/`, and collects the result when it exits. If a separate
scheduler starts agents itself, use `loopq tick --agent NAME` as its precheck.
For a CLI with a model option, set `model` and include `{model}` in that
option's argument. With a manual or external launcher, `model` records the
intended choice but does not change the harness automatically.

`loopq run` gives the agent no standard input. A harness that stops to ask
something, such as a model picker, exits instead of holding the claim until
the lease ends; the fragment is requeued and the agent cools down. Pass every
choice on the command line. For example, OpenCode started through Ollama
needs `--model`, and `run` makes it work without the TUI:

```yaml
  opencode:
    worktree: /absolute/path/project-loop-opencode
    model: qwen3.8:latest
    tiers: [mechanical]
    kinds: [work]
    command: ["ollama", "launch", "opencode", "-y", "--model", "{model}",
              "--", "run", "{prompt}"]
    cron: "15,35,55 * * * *"
```

An Orca automation has no model option. Orca starts OpenCode with
`ollama launch opencode -y`, which opens Ollama's model picker and waits there
until someone answers it. Run such an agent with `command` as above instead of
`launcher: orca`. If a session is already stuck, `loopq handoff ID` stops a
`run` session and requeues its work; close an Orca session yourself.

## Several agents and models

[examples/multi-agent.yaml](examples/multi-agent.yaml) is a complete config
with nine agents across Claude Code, Codex, Cursor, OpenCode, Gemini CLI,
GitHub Copilot CLI, Kiro CLI and Goose, all started by `dispatch`. It splits one harness into two agents with different models:

| Agent | Model | Tiers | Kinds |
|---|---|---|---|
| `claude-opus` | `claude-opus-5-5` | judgement | all |
| `claude-sonnet` | `claude-sonnet-5` | standard, mechanical | work, review, conflict |
| `codex` | Codex default | all | all |
| `cursor` | Cursor default | standard, mechanical | work, review, conflict |
| `opencode` | `qwen3.8:latest` | mechanical | work |
| `gemini` | `gemini-2.5-pro` | standard, mechanical | work, review, conflict |
| `copilot` | `sonnet` | standard, mechanical | work, review, conflict |
| `kiro` | `claude-sonnet-5` | standard, mechanical | work, review, conflict |
| `goose` | `claude-sonnet-5` | standard, mechanical | work |

loopq routes by agent, not by model, so a harness used with two models is
two agents: two names, two worktrees, the same `command` with a different
`model`. Each fragment's `tier` then decides which model can take it, and
`retry ID --tier TIER` moves a fragment to another model.

Things to keep in mind when splitting a harness:

- An agent never reviews its own work, but `claude-opus` can review work by
  `claude-sonnet`. For reviews from a different vendor, leave `review` out of
  one of the two agents' kinds.
- Usage limits usually belong to the account, while cooldowns belong to the
  agent. When one agent hits a shared limit, the other fails on its next run
  and cools down too; `cooldown` shows them all and `cooldown --agent NAME --clear` ends each one.
- Give every tier at least one agent, and every kind a fragment can have.
  Otherwise that work waits in the ready queue; `why AGENT` shows which rule
  excludes it.
- Stagger the `cron` minutes so agents do not all start in the same minute.

The permissions in the example are scoped rather than bypassed. A run that
needs a command outside them fails and is requeued; check
`loopq runs --failed`, then widen the allowlist or sandbox for that agent.

## One cron job for all loops

Put each loop config in one directory, for example `~/.config/loopq/loops.d/`.
Each `.yaml` or `.yml` file is one loop and must have a distinct `project`.
Configs can be symlinks to files kept elsewhere. Agents with a `command` run
locally. Agents with `launcher: orca` trigger an existing Orca automation.
All others remain manual.

```sh
loopq dispatch --dry-run
loopq dispatch
```

The dry run lists due actions and reasons for skips without starting agents.
A normal dispatch starts a separate `run` process for each due command agent,
then returns. A live command agent session is skipped. Each `run` collects a
prior result, takes available work, and exits when its session finishes.
Agent output goes to
`~/.loops/PROJECT/logs/runs/`; runner errors go to
`~/.loops/PROJECT/logs/dispatch-AGENT.log`.

For `launcher: orca`, the dispatcher finds exactly one automation whose
precheck runs `loopq tick --agent NAME --config FILE`. Its schedule must match
the agent's `cron` value. Disable the automation's built-in schedule before
using live dispatch, so the same agent is not scheduled twice. The dispatcher
refuses to trigger an enabled automation. It records successful triggers in
the queue's `ticks/` directory to avoid triggering twice in the same minute.
The Orca app must be running and its CLI must be available as `orca` on
`PATH`, or through `LOOPQ_ORCA_CLI=/absolute/path/to/orca`.

For cron, use one entry and replace the paths with absolute paths on your
machine:

```cron
* * * * * /absolute/path/to/loopq dispatch >>/absolute/path/dispatch.log 2>&1
```

Set cron's `PATH` so the loopq script can find `uv` and `git`, and agent
commands can find their own executables. Create the parent directory for
`dispatch.log` first. Cron can run every minute because the dispatcher checks
each agent's schedule, live command sessions and the Orca trigger stamp.
`dispatch` reports invalid configs and continues with the others.

The queue contains fragments, logs, briefs, claims and cooldown state. It is
local data; uninstalling the `loopq` command does not remove it. The tool
commits successful work, rebases its branch onto `base`, and advances `base`
after a separate review and passing gates. Keep a normal Git backup or remote
for the project branch you care about.
