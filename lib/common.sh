# shellcheck shell=bash
# common.sh — shared utilities. Sourced by `wiki` and other lib/*.sh files.
# Idempotent: guards against double-sourcing via __WIKI_COMMON_LOADED.

[[ -n "${__WIKI_COMMON_LOADED:-}" ]] && return 0
__WIKI_COMMON_LOADED=1

# ── Paths (resolved by the entry script before sourcing this file) ───
: "${WIKI_DIR:?WIKI_DIR must be set by caller}"
: "${ROOT_DIR:?ROOT_DIR must be set by caller}"

LIB_DIR="$WIKI_DIR/lib"
SCRIPTS_DIR="$WIKI_DIR/scripts"
HOOKS_DIR="$WIKI_DIR/hooks"
CONFIG_FILE="$WIKI_DIR/config.yaml"

# Hook-script paths used inside generated agent configs.
# Relative paths (project-scope-only — assume CWD = vault root):
HOOK_SESSION_START_REL=".wiki/hooks/session-start.py"
HOOK_SESSION_END_REL=".wiki/hooks/session-end.py"
HOOK_PRE_COMPACT_REL=".wiki/hooks/pre-compact.py"
# Absolute paths (work for both user and project scope):
HOOK_SESSION_START_ABS="$WIKI_DIR/hooks/session-start.py"
HOOK_SESSION_END_ABS="$WIKI_DIR/hooks/session-end.py"
HOOK_PRE_COMPACT_ABS="$WIKI_DIR/hooks/pre-compact.py"

# ── Engine environment location (the ONE rule; Python reads the result) ──
# A vault inside a cloud-synced folder (iCloud Drive, ~/Library/CloudStorage)
# must not run its Python environment from there: the sync engine evicts file
# contents to save space and re-materialises them on access, and the kernel
# SIGKILLs a mapped executable whose pages stop matching their code signature
# mid-swap (`Taskgated Invalid Signature`, lxw 2026-09-17 — three kills of
# the 200 MB bundled Claude CLI in one night, six-minute imports the same
# evening). A symlink at .wiki/.venv is NOT a fix: iCloud kept the directory
# it already had and shelved the symlink as `.venv 2`. So for such vaults the
# environment lives at ~/.venvs/<vault>-wiki and every uv invocation gets
# told so via UV_PROJECT_ENVIRONMENT — exported here for the dispatcher, and
# written literally into the agent hook commands by lib/agents.sh, because
# hook processes come from the agent, not from `wiki`. An operator-set
# UV_PROJECT_ENVIRONMENT always wins. Elsewhere uv's default (.wiki/.venv)
# stays and this exports nothing.
wiki_path_is_cloud_synced() {
  case "$1" in
    */Library/Mobile\ Documents/*|*/Library/CloudStorage/*) return 0 ;;
    *) return 1 ;;
  esac
}
wiki_venv_dir() {
  if [[ -n "${UV_PROJECT_ENVIRONMENT:-}" ]]; then
    printf "%s" "$UV_PROJECT_ENVIRONMENT"
  elif wiki_path_is_cloud_synced "$WIKI_DIR"; then
    printf "%s/.venvs/%s-wiki" "$HOME" "$(basename "$ROOT_DIR")"
  fi
}
WIKI_VENV_DIR="$(wiki_venv_dir)"
if [[ -n "$WIKI_VENV_DIR" ]]; then
  export UV_PROJECT_ENVIRONMENT="$WIKI_VENV_DIR"
fi

# ── Commands for another shell ───────────────────────────────────────
# A path inside a command that some other shell runs (an agent's hook, a hint the
# operator pastes) is single-quoted, each ' in it written as '\''. Bare '…' broke on
# an apostrophe ("Alex's Vault": every hook died on a syntax error), an unquoted path
# on a space (every iCloud vault's `Mobile Documents`). Pattern removal rather than
# ${s//…/…}: bash 5.2's patsub_replacement reads that replacement differently from
# the macOS bash 3.2.
shell_quote() {
  local s="$1" out=""
  while [[ "$s" == *\'* ]]; do
    out+="${s%%\'*}'\\''"
    s="${s#*\'}"
  done
  printf "'%s'" "$out$s"
}

# The `uv sync` an operator can paste. Their shell never had the export above, so
# the environment is named; a bare `uv sync` would rebuild .wiki/.venv inside a
# cloud-synced vault and leave the engine's own environment as it was.
sync_hint() {
  printf "UV_PROJECT_ENVIRONMENT=%s uv sync --project %s" \
    "$(shell_quote "${UV_PROJECT_ENVIRONMENT:-$WIKI_DIR/.venv}")" "$(shell_quote "$WIKI_DIR")"
}

# ── Colors / output ──────────────────────────────────────────────────
if [[ -t 1 ]]; then
  C_RESET=$'\e[0m'; C_DIM=$'\e[2m'; C_BOLD=$'\e[1m'
  C_GREEN=$'\e[32m'; C_YELLOW=$'\e[33m'; C_RED=$'\e[31m'; C_BLUE=$'\e[34m'; C_CYAN=$'\e[36m'
else
  C_RESET=""; C_DIM=""; C_BOLD=""; C_GREEN=""; C_YELLOW=""; C_RED=""; C_BLUE=""; C_CYAN=""
fi

say()  { printf "%s\n" "$*"; }
info() { printf "%s%s%s\n" "$C_BLUE" "$*" "$C_RESET"; }
ok()   { printf "%s✓ %s%s\n" "$C_GREEN" "$*" "$C_RESET"; }
warn() { printf "%s! %s%s\n" "$C_YELLOW" "$*" "$C_RESET"; }
err()  { printf "%s✗ %s%s\n" "$C_RED" "$*" "$C_RESET" >&2; }
die()  { err "$*"; exit 1; }

banner() {
  printf "%s%s%s\n" "$C_BOLD" "$1" "$C_RESET"
  [[ -n "${2:-}" ]] && printf "%s%s%s\n" "$C_DIM" "$2" "$C_RESET"
  echo
}

# ── Tooling guards ───────────────────────────────────────────────────
require_cmd() {
  local cmd="$1" reason="${2:-required}"
  command -v "$cmd" >/dev/null 2>&1 || die "$cmd not found ($reason). Install it and retry."
}

# ── Backup helper (lib/agents.sh's install + uninstall) ──────────────
# <file>.bak.<YYYYmmdd-HHMMSS>, never over an earlier backup: an install and an uninstall
# within one second took the same name, and the second copy replaced the first (the
# pre-install original). A clash takes -2, -3, …. Prints the backup's path; a failed copy
# returns 1, so a caller can stop before it writes.
backup_file() {
  local f="$1"
  [[ -f "$f" ]] || return 0
  local stamp; stamp="$(date +%Y%m%d-%H%M%S)"
  local bak="${f}.bak.$stamp" n=1
  while [[ -e "$bak" ]]; do
    n=$((n + 1))
    bak="${f}.bak.$stamp-$n"
  done
  cp "$f" "$bak" || return 1
  printf "%s" "$bak"
}
