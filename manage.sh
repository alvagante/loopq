#!/usr/bin/env bash
set -euo pipefail

usage() {
    printf 'Usage: %s install|uninstall [--dry-run]\n' "$0"
    printf 'Creates or removes a symlink to this checkout in LOOPQ_BIN_DIR (default ~/.local/bin).\n'
}

if [[ $# -lt 1 || $# -gt 2 || ( $# -eq 2 && $2 != --dry-run ) ]]; then
    usage >&2
    exit 2
fi

action=$1
dry_run=${2:-}
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
source_file=$source_dir/loopq.py
bin_dir=${LOOPQ_BIN_DIR:-$HOME/.local/bin}
link=$bin_dir/loopq

case $action in
    install)
        if [[ -e $link || -L $link ]]; then
            if [[ -L $link && $(readlink -- "$link") == "$source_file" ]]; then
                printf 'Already installed: %s -> %s\n' "$link" "$source_file"
                exit 0
            fi
            printf 'Refusing to replace existing path: %s\n' "$link" >&2
            exit 1
        fi
        printf 'Create %s -> %s\n' "$link" "$source_file"
        printf 'Keep this checkout in place. loopq needs uv and git on PATH.\n'
        if [[ $dry_run != --dry-run ]]; then
            mkdir -p -- "$bin_dir"
            ln -s -- "$source_file" "$link"
        fi
        ;;
    uninstall)
        if [[ ! -e $link && ! -L $link ]]; then
            printf 'Nothing to remove: %s does not exist.\n' "$link"
            exit 0
        fi
        if [[ ! -L $link || $(readlink -- "$link") != "$source_file" ]]; then
            printf 'Refusing to remove a path not installed from this checkout: %s\n' "$link" >&2
            exit 1
        fi
        printf 'Remove symlink %s -> %s\n' "$link" "$source_file"
        printf 'Queue data, configs, worktrees and this checkout stay in place.\n'
        if [[ $dry_run != --dry-run ]]; then
            rm -- "$link"
        fi
        ;;
    -h|--help|help)
        usage
        ;;
    *)
        usage >&2
        exit 2
        ;;
esac
