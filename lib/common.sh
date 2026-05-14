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
WIKI_CONFIG_PY="$SCRIPTS_DIR/core/config.py"

# Hook-script paths used inside generated agent configs.
# Relative paths (project-scope-only — assume CWD = vault root):
HOOK_SESSION_START_REL=".wiki/hooks/session-start.py"
HOOK_SESSION_END_REL=".wiki/hooks/session-end.py"
HOOK_PRE_COMPACT_REL=".wiki/hooks/pre-compact.py"
# Absolute paths (work for both user and project scope):
HOOK_SESSION_START_ABS="$WIKI_DIR/hooks/session-start.py"
HOOK_SESSION_END_ABS="$WIKI_DIR/hooks/session-end.py"
HOOK_PRE_COMPACT_ABS="$WIKI_DIR/hooks/pre-compact.py"

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

# ── Backup helper (used by hooks + config writers) ───────────────────
backup_file() {
  local f="$1"
  [[ -f "$f" ]] || return 0
  local bak="${f}.bak.$(date +%Y%m%d-%H%M%S)"
  cp "$f" "$bak"
  printf "%s" "$bak"
}
