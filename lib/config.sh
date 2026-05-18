# shellcheck shell=bash
# config.sh — wraps the Python core/config.py CLI for bash callers and
# defines the interactive setup wizard / config editor.

[[ -n "${__WIKI_CONFIG_LOADED:-}" ]] && return 0
__WIKI_CONFIG_LOADED=1

# Run the python config CLI quietly. --project pins uv to .wiki/pyproject.toml
# so it works regardless of the user's CWD when they invoke `wiki`.
_wiki_config_py() {
  uv run --quiet --project "$WIKI_DIR" python "$WIKI_CONFIG_PY" "$@" \
    2> >(grep -v '^warning:.*VIRTUAL_ENV' >&2)
}

config_get()  { _wiki_config_py get  "$1"; }
config_set()  { _wiki_config_py set  "$1" "$2"; }
config_keys() { _wiki_config_py keys; }
config_path() { _wiki_config_py path; }

# Probe an Ollama base URL. Returns 0 if reachable.
_probe_ollama() {
  local url="$1"
  curl -sSf --max-time 3 "${url%/}/api/tags" >/dev/null 2>&1
}

_validate_compile_hour() { [[ "$1" =~ ^([0-9]|1[0-9]|2[0-3])$ ]] || { warn "Hour must be 0–23"; return 1; }; }
_validate_url()          { [[ "$1" =~ ^https?:// ]] || { warn "Must start with http:// or https://"; return 1; }; }

# ── Setup wizard (first-time) ────────────────────────────────────────
# Asks the 6 questions worth asking, writes answers to config.yaml.
config_cmd_setup_wizard() {
  banner "wiki config — setup wizard" \
    "6 questions. Skip with Enter to keep the current value."
  echo

  # 1. Ollama URL
  local current_url; current_url="$(config_get models.ollama_url)"
  local url
  url="$(ask "Ollama base URL" "$current_url" _validate_url)"
  if [[ "$url" != "$current_url" ]]; then
    config_set models.ollama_url "$url"
  fi
  if _probe_ollama "$url"; then
    ok "Ollama reachable at $url"
    local enable_local=1
  else
    warn "Ollama NOT reachable at $url — local-LLM features will fail."
    local enable_local=0
  fi

  echo
  # 2. Compile model
  local current_model; current_model="$(config_get models.compile_model)"
  info "Compile model — Claude tier for compile.py and retry-failed-flushes.py"
  # Resolve default-index in plain shell BEFORE calling select_one. macOS
  # bash 3.2 mis-parses nested $( case … esac ) inside another $( … ) with
  # case-pattern ')' tokens (syntax error: unexpected newline near *)).
  local model_default_idx
  case "$current_model" in
    claude-opus-4-7)   model_default_idx=1 ;;
    claude-sonnet-4-6) model_default_idx=2 ;;
    claude-haiku-4-5)  model_default_idx=3 ;;
    *)                 model_default_idx=1 ;;
  esac
  local model
  model="$(select_one "Pick" "claude-opus-4-7|claude-sonnet-4-6|claude-haiku-4-5" "$model_default_idx")"
  if [[ "$model" != "$current_model" ]]; then
    config_set models.compile_model "$model"
  fi

  echo
  # 3. Compile after hour
  local current_hour; current_hour="$(config_get scheduling.compile_after_hour)"
  local hour
  hour="$(ask "Auto-compile starts at hour (0-23, local time)" "$current_hour" _validate_compile_hour)"
  if [[ "$hour" != "$current_hour" ]]; then
    config_set scheduling.compile_after_hour "$hour"
  fi

  echo
  # 4. Procmail execution (default OFF — destructive without webmail-procmail provider setup)
  info "Procmail execution lets suggestions/cli.py call a webmail-procmail provider API to apply mail rules server-side."
  warn "Default OFF. Only enable if you have a procmail-capable webmail account configured (e.g. All-Inkl kasserver)."
  local procmail_default="n"
  [[ "$(config_get features.procmail_execution)" == "True" ]] && procmail_default="y"
  if confirm "Enable procmail execution?" "$procmail_default"; then
    config_set features.procmail_execution true
  else
    config_set features.procmail_execution false
  fi

  echo
  # 5. Local-LLM features (curiosity loop + vision screenshots) — bundled
  if (( enable_local == 1 )); then
    local default_local="y"
  else
    local default_local="n"
  fi
  if confirm "Enable local-LLM features (curiosity loop + screenshot OCR)?" "$default_local"; then
    config_set features.curiosity_loop true
    config_set features.vision_screenshots true
  else
    config_set features.curiosity_loop false
    config_set features.vision_screenshots false
  fi

  echo
  # 6. Global skill install — make `use-llm-wiki` reachable from any project.
  info "Global skill install links the 'use-llm-wiki' skill into ~/.claude/skills/"
  info "so an agent working in *any* project can discover and query this wiki."
  local global_default="n"
  [[ "$(config_get skills.global_install)" == "True" ]] && global_default="y"
  if confirm "Make this wiki's use-llm-wiki skill globally available?" "$global_default"; then
    config_set skills.global_install true
  else
    config_set skills.global_install false
  fi

  echo
  ok "Wizard complete. Config written to $(config_path)."
}

# ── Interactive editor (post-setup reconfig) ─────────────────────────
# Loop: show sections → pick section → list keys → pick key → enter value.
config_cmd_edit() {
  banner "wiki config — edit" "Pick a section, then a key. Enter on a key skips it."
  while :; do
    echo
    local section
    section="$(select_one "Section" "models|scheduling|features|piggybacks|limits|graph_view|skills|exit" 8)"
    [[ "$section" == "exit" ]] && break

    # Build the key list under this section.
    local -a keys=()
    while IFS= read -r k; do
      [[ "$k" == "$section."* ]] && keys+=("$k")
    done < <(config_keys)
    if [[ ${#keys[@]} -eq 0 ]]; then
      warn "No keys in $section."
      continue
    fi

    echo
    printf "%sCurrent values in %s:%s\n" "$C_DIM" "$section" "$C_RESET"
    local i=1
    for k in "${keys[@]}"; do
      local v; v="$(config_get "$k" 2>/dev/null || echo '?')"
      printf "  %d) %-50s = %s\n" "$i" "$k" "$v"
      i=$((i+1))
    done
    printf "Pick a key to edit ${C_DIM}(number, or 'b' to go back)${C_RESET}: "
    local pick; read -r pick
    [[ "$pick" == "b" || -z "$pick" ]] && continue
    [[ "$pick" =~ ^[0-9]+$ ]] || { warn "Invalid pick."; continue; }
    (( pick >= 1 && pick <= ${#keys[@]} )) || { warn "Out of range."; continue; }

    local key="${keys[$((pick-1))]}"
    local current; current="$(config_get "$key")"
    echo
    local new
    printf "Set %s ${C_DIM}[current: %s]${C_RESET}: " "$key" "$current"
    read -r new
    if [[ -z "$new" ]]; then
      info "skipped"
      continue
    fi
    if config_set "$key" "$new"; then
      ok "$key = $new"
    fi
  done
  echo
  ok "Done."
}

# Print compact config summary.
config_cmd_status() {
  banner "wiki config — status"
  printf "%-40s %s\n" "config.yaml" "$(config_path)"
  printf "%-40s %s\n" "compile_model" "$(config_get models.compile_model)"
  printf "%-40s %s\n" "ollama_url" "$(config_get models.ollama_url)"
  printf "%-40s %s\n" "compile_after_hour" "$(config_get scheduling.compile_after_hour)"
  printf "%-40s %s\n" "features.curiosity_loop" "$(config_get features.curiosity_loop)"
  printf "%-40s %s\n" "features.vision_screenshots" "$(config_get features.vision_screenshots)"
  printf "%-40s %s\n" "features.procmail_execution" "$(config_get features.procmail_execution)"
  printf "%-40s %s\n" "skills.global_install" "$(config_get skills.global_install)"
  echo
  if _probe_ollama "$(config_get models.ollama_url)"; then
    ok "Ollama reachable"
  else
    warn "Ollama unreachable at $(config_get models.ollama_url)"
  fi
}
