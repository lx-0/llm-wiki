# shellcheck shell=bash
# config.sh — wraps the Python core/config.py CLI for bash callers and
# defines the interactive setup wizard / config editor.

[[ -n "${__WIKI_CONFIG_LOADED:-}" ]] && return 0
__WIKI_CONFIG_LOADED=1

# Run the python config CLI quietly. --project pins uv to .wiki/pyproject.toml
# so it works regardless of the user's CWD when they invoke `wiki`. Run as a
# module with scripts/ on PYTHONPATH (core.entry's shape) — core/config.py has
# no sys.path bootstrap of its own any more (M033-S02).
_wiki_config_py() {
  PYTHONPATH="$SCRIPTS_DIR" uv run --quiet --project "$WIKI_DIR" python -m core.config "$@" \
    2> >(grep -v '^warning:.*VIRTUAL_ENV' >&2)
}

# What is left here serves the callers M034 has not ported yet (reassessment after S01):
# the setup wizard (S02-T03) and lib/skills.sh's config_get (S03). `wiki config` itself is
# Python since S02-T02 (scripts/config_cli.py).
config_get()  { _wiki_config_py get  "$1"; }
config_set()  { _wiki_config_py set  "$1" "$2"; }
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
  info "Compile model — Claude tier for compile.py and retry_failed_flushes.py"
  # Resolve default-index in plain shell BEFORE calling select_one. macOS
  # bash 3.2 mis-parses nested $( case … esac ) inside another $( … ) with
  # case-pattern ')' tokens (syntax error: unexpected newline near *)).
  # The `*)` catch-all MUST map to the CURRENT engine default (claude-opus-4-8):
  # with the retired 4-7 as option 1 it actively DOWNGRADED a default install —
  # `config_get` returned 4-8, the catch-all picked index 1 = 4-7, and pressing
  # Enter wrote the retired model that the next `wiki update` migration
  # (MODEL_UPGRADES) bumped right back. Wizard and migration undoing each other.
  local model_default_idx
  case "$current_model" in
    claude-opus-4-8)   model_default_idx=1 ;;
    claude-sonnet-4-6) model_default_idx=2 ;;
    claude-haiku-4-5)  model_default_idx=3 ;;
    *)                 model_default_idx=1 ;;
  esac
  local model
  model="$(select_one "Pick" "claude-opus-4-8|claude-sonnet-4-6|claude-haiku-4-5" "$model_default_idx")"
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
