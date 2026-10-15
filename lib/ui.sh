# shellcheck shell=bash
# ui.sh — interactive prompts. No business logic, only input/output.

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

# ask "Prompt" [default] [validator_fn]
# Reads a line, returns it (echoed) — validator_fn can re-prompt by returning 1.
# Prompt + hints go to stderr so callers can capture the answer with $(ask …)
# without the prompt-text leaking into the captured value. Without this, the
# user sees an apparent hang (prompt swallowed by command substitution) and
# whatever they type ends up concatenated with the prompt as the "answer".
ask() {
  local prompt="$1" default="${2:-}" validator="${3:-}"
  local hint=""
  [[ -n "$default" ]] && hint=" ${C_DIM}[$default]${C_RESET}"
  while :; do
    printf "%s%s: " "$prompt" "$hint" >&2
    local input; read -r input
    input="${input:-$default}"
    if [[ -n "$validator" ]]; then
      if ! "$validator" "$input"; then
        continue
      fi
    fi
    printf "%s" "$input"
    return 0
  done
}

# select_one "Prompt" "opt1|opt2|opt3" [default_index_1based]
# Echoes the chosen option string.
select_one() {
  local prompt="$1" options_str="$2" default_idx="${3:-1}"
  local IFS='|'
  read -r -a options <<< "$options_str"
  local i=1
  for opt in "${options[@]}"; do
    local marker="  "
    [[ "$i" == "$default_idx" ]] && marker="${C_GREEN}*${C_RESET} "
    printf "  %s%d) %s\n" "$marker" "$i" "$opt" >&2
    i=$((i+1))
  done
  printf "%s [%s]: " "$prompt" "$default_idx" >&2
  local input; read -r input
  input="${input:-$default_idx}"
  [[ "$input" =~ ^[0-9]+$ ]] || input="$default_idx"
  if (( input < 1 || input > ${#options[@]} )); then
    input="$default_idx"
  fi
  printf "%s" "${options[$((input-1))]}"
}

# select_many "Prompt" "opt1|opt2|opt3" "default_csv"
# Returns chosen options newline-separated on stdout.
# Empty input → defaults. Numbers: space-separated 1-based.
select_many() {
  local prompt="$1" options_str="$2" default_csv="${3:-}"
  local IFS='|'
  read -r -a options <<< "$options_str"
  local i=1
  for opt in "${options[@]}"; do
    local marker="  "
    [[ ",$default_csv," == *",$opt,"* ]] && marker="${C_GREEN}*${C_RESET} "
    printf "  %s%d) %s\n" "$marker" "$i" "$opt" >&2
    i=$((i+1))
  done
  printf "%s${C_DIM} (space-separated numbers, Enter for defaults marked *)${C_RESET}: " \
    "$prompt" >&2
  local input; read -r input
  local -a chosen=() numbers=()
  if [[ -z "$input" ]]; then
    IFS=',' read -r -a chosen <<< "$default_csv"
  else
    # Split on spaces explicitly: the function-wide IFS='|' made "1 2 3" one token, so a
    # typed multi-selection matched no number and came back empty.
    IFS=' ' read -r -a numbers <<< "$input"
    for n in "${numbers[@]}"; do
      [[ "$n" =~ ^[0-9]+$ ]] || continue
      (( n >= 1 && n <= ${#options[@]} )) || continue
      chosen+=("${options[$((n-1))]}")
    done
  fi
  # An empty array expands as "unbound" under `set -u` in bash < 4.4 (macOS /bin/bash).
  (( ${#chosen[@]} > 0 )) && printf "%s\n" "${chosen[@]}"
  return 0
}

# pause "Press Enter to continue"
pause() {
  printf "%s%s%s " "$C_DIM" "${1:-Press Enter to continue}" "$C_RESET"
  read -r
}
