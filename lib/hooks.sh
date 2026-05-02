# shellcheck shell=bash
# hooks.sh — interactive flows for `wiki hooks {install,uninstall,status}`.
# Composes ui.sh prompts + agents.sh installers.

[[ -n "${__WIKI_HOOKS_LOADED:-}" ]] && return 0
__WIKI_HOOKS_LOADED=1

# Print install status table.
hooks_status_table() {
  printf "%-10s %-22s %-22s %s\n" "AGENT" "USER" "PROJECT" "PROJECT CONFIG"
  printf "%s\n" "──────────────────────────────────────────────────────────────────────────────"
  for entry in "${WIKI_AGENTS[@]}"; do
    IFS='|' read -r name _ _ <<< "$entry"
    local user_cfg proj_cfg user_status proj_status
    user_cfg="$(agent_config_path "$name" user)"
    proj_cfg="$(agent_config_path "$name" project)"
    user_status="${C_DIM}—${C_RESET}"
    proj_status="${C_DIM}—${C_RESET}"
    agent_present "$name" user && user_status="${C_DIM}detected${C_RESET}"
    agent_present "$name" project && proj_status="${C_DIM}detected${C_RESET}"
    hooks_installed "$user_cfg" && user_status="${C_GREEN}installed${C_RESET}"
    hooks_installed "$proj_cfg" && proj_status="${C_GREEN}installed${C_RESET}"
    printf "%-10s %-30s %-30s %s\n" "$name" "$user_status" "$proj_status" "$proj_cfg"
  done
}

# Build comma-separated list of agents that match a predicate (passed as fn name).
_filter_agents() {
  local predicate="$1"
  local out=""
  for entry in "${WIKI_AGENTS[@]}"; do
    IFS='|' read -r name _ _ <<< "$entry"
    if "$predicate" "$name"; then
      out+="${out:+,}$name"
    fi
  done
  printf "%s" "$out"
}

_agent_detected_anywhere() {
  agent_present "$1" user || agent_present "$1" project
}

_agent_has_wiki_hooks() {
  hooks_installed "$(agent_config_path "$1" user)" || hooks_installed "$(agent_config_path "$1" project)"
}

# Prompt user to pick scope. Echoes one or both of: "user" "project".
_prompt_scope() {
  echo
  local choice
  choice="$(select_one "Install scope" "project only|user only|both" 1)"
  case "$choice" in
    "project only") echo "project" ;;
    "user only") echo "user" ;;
    "both") echo "project user" ;;
  esac
}

hooks_cmd_install() {
  banner "wiki hooks — install" \
    "Adds session hooks to one or more AI agent configs. Backups + idempotent."
  hooks_status_table
  echo

  local default_csv; default_csv="$(_filter_agents _agent_detected_anywhere)"
  [[ -z "$default_csv" ]] && default_csv="claude"

  local -a agents=()
  while IFS= read -r line; do agents+=("$line"); done < <(
    select_many "Select agents to install hooks for" "$(agent_names)" "$default_csv"
  )
  if [[ ${#agents[@]} -eq 0 ]]; then
    warn "No agents selected."; return 0
  fi

  local scopes; scopes="$(_prompt_scope)"

  echo
  info "Will install hooks:"
  for a in "${agents[@]}"; do
    for s in $scopes; do
      printf "  - %s @ %s → %s\n" "$a" "$s" "$(agent_config_path "$a" "$s")"
    done
  done
  echo
  if ! confirm "Proceed?" y; then warn "Aborted."; return 0; fi

  echo
  for a in "${agents[@]}"; do
    for s in $scopes; do
      install_one "$a" "$s" || true
    done
  done
  echo
  ok "Done. Restart agent CLIs to pick up the new hooks."
}

hooks_cmd_uninstall() {
  banner "wiki hooks — uninstall" "Removes wiki-managed hook entries; preserves user's other hooks."
  hooks_status_table
  echo

  local default_csv; default_csv="$(_filter_agents _agent_has_wiki_hooks)"
  if [[ -z "$default_csv" ]]; then
    warn "No wiki hooks installed anywhere."
    return 0
  fi

  local -a agents=()
  while IFS= read -r line; do agents+=("$line"); done < <(
    select_many "Select agents to uninstall hooks from" "$(agent_names)" "$default_csv"
  )
  [[ ${#agents[@]} -eq 0 ]] && { warn "No agents selected."; return 0; }

  local scopes; scopes="$(_prompt_scope)"
  echo
  if ! confirm "Remove wiki hooks from selected configs?" y; then warn "Aborted."; return 0; fi

  echo
  for a in "${agents[@]}"; do
    for s in $scopes; do
      uninstall_one "$a" "$s" || true
    done
  done
  echo
  ok "Done."
}

hooks_cmd_status() {
  banner "wiki hooks — status"
  hooks_status_table
}
