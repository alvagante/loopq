#!/usr/bin/env bash
set -euo pipefail

usage() {
    printf 'Usage: %s install|uninstall [--dry-run] [--skill|--no-skill]\n' "$0"
    printf 'Creates or removes a symlink to this checkout in LOOPQ_BIN_DIR (default ~/.local/bin).\n'
    printf 'install may also symlink the loopq skill into skill dirs for agent harnesses on PATH.\n'
    printf '--skill installs the skill without asking; --no-skill skips it. Default is to ask on a TTY.\n'
}

action=
dry_run=
skill_mode=ask
for arg in "$@"; do
    case $arg in
        install|uninstall|-h|--help|help)
            if [[ -n $action ]]; then
                usage >&2
                exit 2
            fi
            action=$arg
            ;;
        --dry-run) dry_run=--dry-run ;;
        --skill) skill_mode=yes ;;
        --no-skill) skill_mode=no ;;
        *)
            usage >&2
            exit 2
            ;;
    esac
done

if [[ -z $action ]]; then
    usage >&2
    exit 2
fi

source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
source_file=$source_dir/loopq.py
skill_src=$source_dir/skills/loopq
skill_name=loopq
legacy_skill_name=loopq-setup
bin_dir=${LOOPQ_BIN_DIR:-$HOME/.local/bin}
link=$bin_dir/loopq
config_home=${XDG_CONFIG_HOME:-$HOME/.config}

# binary|label|global skills directory (relative to $HOME unless absolute via config_home)
# Keep in sync with harnesses that loopq create detects.
skill_harnesses=(
    "claude|Claude Code|$HOME/.claude/skills"
    "codex|Codex|$HOME/.codex/skills"
    "cursor-agent|Cursor|$HOME/.cursor/skills"
    "agent|Cursor|$HOME/.cursor/skills"
    "opencode|OpenCode|$config_home/opencode/skills"
    "gemini|Gemini CLI|$HOME/.gemini/skills"
    "copilot|GitHub Copilot|$HOME/.copilot/skills"
    "kiro-cli|Kiro CLI|$HOME/.kiro/skills"
    "goose|Goose|$config_home/goose/skills"
    "amp|Amp|$config_home/agents/skills"
    "droid|Droid|$HOME/.factory/skills"
    "crush|Crush|$config_home/crush/skills"
    "qwen|Qwen Code|$HOME/.qwen/skills"
    "pi|Pi|$HOME/.pi/agent/skills"
)

symlink_target() {
    # Prefer GNU -f when available; fall back to plain readlink.
    if readlink -f -- "$1" >/dev/null 2>&1; then
        readlink -f -- "$1"
    else
        readlink -- "$1"
    fi
}

discover_skill_targets() {
    # Prints unique "label|dir" lines for harnesses found on PATH.
    local seen_dirs= entry binary label dir
    for entry in "${skill_harnesses[@]}"; do
        IFS='|' read -r binary label dir <<<"$entry"
        if ! command -v -- "$binary" >/dev/null 2>&1; then
            continue
        fi
        case "|$seen_dirs|" in
            *"|$dir|"*) continue ;;
        esac
        seen_dirs=${seen_dirs:+$seen_dirs|}$dir
        printf '%s|%s\n' "$label" "$dir"
    done
}

remove_legacy_skill_links() {
    # Drop loopq-setup symlinks that pointed at this checkout's old skill path.
    local entry dir target
    for entry in "${skill_harnesses[@]}"; do
        IFS='|' read -r _ _ dir <<<"$entry"
        target=$dir/$legacy_skill_name
        if [[ ! -L $target ]]; then
            continue
        fi
        case $(symlink_target "$target") in
            "$source_dir"/skills/*)
                printf 'Remove legacy skill symlink %s\n' "$target"
                if [[ $dry_run != --dry-run ]]; then
                    rm -- "$target"
                fi
                ;;
        esac
    done
}

install_skill_links() {
    local targets=() line label dir target
    while IFS= read -r line; do
        [[ -n $line ]] || continue
        targets+=("$line")
    done < <(discover_skill_targets)

    if [[ ${#targets[@]} -eq 0 ]]; then
        printf 'No known agent harnesses found on PATH; skipping skill install.\n'
        return 0
    fi

    printf 'Detected agent harnesses and skill directories:\n'
    for line in "${targets[@]}"; do
        IFS='|' read -r label dir <<<"$line"
        printf '  %s -> %s/%s\n' "$label" "$dir" "$skill_name"
    done

    local do_install=$skill_mode
    if [[ $do_install == ask ]]; then
        if [[ $dry_run == --dry-run ]]; then
            printf 'Would ask to install the loopq skill into those directories.\n'
            return 0
        fi
        if [[ ! -t 0 ]]; then
            printf 'Skipping skill install (no TTY). Re-run with --skill to install.\n'
            return 0
        fi
        local reply=
        printf 'Install the loopq skill into those directories? [Y/n] '
        read -r reply || true
        case ${reply:-Y} in
            Y|y|yes|YES) do_install=yes ;;
            *) do_install=no ;;
        esac
    fi

    if [[ $do_install != yes ]]; then
        printf 'Skipping skill install.\n'
        return 0
    fi

    if [[ ! -f $skill_src/SKILL.md ]]; then
        printf 'Refusing to install skill: missing %s/SKILL.md\n' "$skill_src" >&2
        return 1
    fi

    remove_legacy_skill_links

    for line in "${targets[@]}"; do
        IFS='|' read -r label dir <<<"$line"
        target=$dir/$skill_name
        if [[ -e $target || -L $target ]]; then
            if [[ -L $target && $(symlink_target "$target") == "$skill_src" ]]; then
                printf 'Skill already installed for %s: %s -> %s\n' "$label" "$target" "$skill_src"
                continue
            fi
            printf 'Refusing to replace existing skill path: %s\n' "$target" >&2
            return 1
        fi
        printf 'Create skill %s -> %s (%s)\n' "$target" "$skill_src" "$label"
        if [[ $dry_run != --dry-run ]]; then
            mkdir -p -- "$dir"
            ln -s -- "$skill_src" "$target"
        fi
    done
}

uninstall_skill_links() {
    local entry dir target
    local removed=0
    remove_legacy_skill_links
    for entry in "${skill_harnesses[@]}"; do
        IFS='|' read -r _ _ dir <<<"$entry"
        target=$dir/$skill_name
        if [[ ! -L $target ]]; then
            continue
        fi
        if [[ $(symlink_target "$target") != "$skill_src" ]]; then
            continue
        fi
        printf 'Remove skill symlink %s -> %s\n' "$target" "$skill_src"
        if [[ $dry_run != --dry-run ]]; then
            rm -- "$target"
        fi
        removed=1
    done
    if [[ $removed -eq 0 ]]; then
        printf 'No loopq skill symlinks from this checkout to remove.\n'
    fi
}

case $action in
    install)
        if [[ -e $link || -L $link ]]; then
            if [[ -L $link && $(symlink_target "$link") == "$source_file" ]]; then
                printf 'Already installed: %s -> %s\n' "$link" "$source_file"
            else
                printf 'Refusing to replace existing path: %s\n' "$link" >&2
                exit 1
            fi
        else
            printf 'Create %s -> %s\n' "$link" "$source_file"
            printf 'Keep this checkout in place. loopq needs uv and git on PATH.\n'
            if [[ $dry_run != --dry-run ]]; then
                mkdir -p -- "$bin_dir"
                ln -s -- "$source_file" "$link"
            fi
        fi
        if [[ $skill_mode != no ]]; then
            install_skill_links
        else
            printf 'Skipping skill install (--no-skill).\n'
        fi
        ;;
    uninstall)
        if [[ ! -e $link && ! -L $link ]]; then
            printf 'Nothing to remove: %s does not exist.\n' "$link"
        elif [[ ! -L $link || $(symlink_target "$link") != "$source_file" ]]; then
            printf 'Refusing to remove a path not installed from this checkout: %s\n' "$link" >&2
            exit 1
        else
            printf 'Remove symlink %s -> %s\n' "$link" "$source_file"
            printf 'Queue data, configs, worktrees and this checkout stay in place.\n'
            if [[ $dry_run != --dry-run ]]; then
                rm -- "$link"
            fi
        fi
        uninstall_skill_links
        ;;
    -h|--help|help)
        usage
        ;;
    *)
        usage >&2
        exit 2
        ;;
esac
