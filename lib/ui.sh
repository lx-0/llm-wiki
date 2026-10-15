# shellcheck shell=bash
# ui.sh — interactive prompts. No business logic, only input/output.
# Python has its own since M034-S02-T01 (core/console: confirm / ask / select_* / pause).
# What is left here serves cmd_update's stash prompt (S05); the file goes with that last
# caller in S05-T04. `ask` went with the wizard (S02-T03), `pause` had no caller left, and
# `select_one` / `select_many` went with lib/hooks.sh (S03-T07).

[[ -n "${__WIKI_UI_LOADED:-}" ]] && return 0
__WIKI_UI_LOADED=1

# confirm "Question?" [y|n]
# Returns 0 on yes, 1 on no. Accepts y/Y/j/J as yes (English/German).
confirm() {
  local prompt="$1" default="${2:-y}"
  local hint="[Y/n]"
  [[ "$default" == "n" ]] && hint="[y/N]"
  printf "%s %s " "$prompt" "$hint"
  local input; read -r input
  input="${input:-$default}"
  [[ "$input" =~ ^[yYjJ] ]]
}
