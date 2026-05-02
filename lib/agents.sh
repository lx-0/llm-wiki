# shellcheck shell=bash
# agents.sh — agent registry + per-agent config writers.
# Pure data and small functions, no UI here.

[[ -n "${__WIKI_AGENTS_LOADED:-}" ]] && return 0
__WIKI_AGENTS_LOADED=1

# Agent registry: name | detection-dir | config-file (relative to scope dir)
WIKI_AGENTS=(
  "claude|.claude|.claude/settings.json"
  "codex|.codex|.codex/hooks.json"
  "gemini|.gemini|.gemini/settings.json"
  "cursor|.cursor|.cursor/hooks.json"
)

# Pretty list of just agent names.
agent_names() {
  local out=""
  for entry in "${WIKI_AGENTS[@]}"; do
    IFS='|' read -r name _ _ <<< "$entry"
    out+="${out:+|}$name"
  done
  printf "%s" "$out"
}

agent_field() {
  local agent="$1" field="$2"
  for entry in "${WIKI_AGENTS[@]}"; do
    IFS='|' read -r name detect config <<< "$entry"
    [[ "$name" == "$agent" ]] || continue
    case "$field" in detect) printf "%s" "$detect" ;; config) printf "%s" "$config" ;; esac
    return
  done
  return 1
}

# scope_dir <user|project>
scope_dir() {
  case "$1" in
    user) printf "%s" "$HOME" ;;
    project) printf "%s" "$ROOT_DIR" ;;
    *) return 1 ;;
  esac
}

agent_present() {
  local agent="$1" scope="$2"
  local detect; detect="$(agent_field "$agent" detect)"
  local sd; sd="$(scope_dir "$scope")"
  [[ -d "$sd/$detect" ]]
}

agent_config_path() {
  local agent="$1" scope="$2"
  printf "%s/%s" "$(scope_dir "$scope")" "$(agent_field "$agent" config)"
}

# Returns 0 if our hooks are present in the agent's config.
# Match heuristic: any reference to one of the engine's hook scripts that also
# sits under a `.wiki/` path. Covers both the current install format
# (`uv run --project .wiki python .wiki/hooks/session-start.py`) and the older
# `cd '...wiki' && uv run python hooks/session-start.py` style some installs
# still carry from earlier engine versions.
hooks_installed() {
  local cfg="$1"
  [[ -f "$cfg" ]] || return 1
  grep -qE "\.wiki['\"/ ].*hooks/(session-(start|end)|pre-compact|_transcript)" "$cfg" 2>/dev/null
}

# ── Hook payload generators ──────────────────────────────────────────
# Each writes a JSON object to stdout with the wiki-managed hooks block.
# Generators omit events the agent doesn't support (e.g. Codex has no PreCompact).

claude_hooks_payload() {
  jq -n \
    --arg start "uv run --project .wiki python $HOOK_SESSION_START_REL" \
    --arg end "uv run --project .wiki python $HOOK_SESSION_END_REL" \
    --arg compact "uv run --project .wiki python $HOOK_PRE_COMPACT_REL" \
    '{
      hooks: {
        SessionStart: [{matcher:"", hooks:[{type:"command", command:$start, timeout:15}]}],
        SessionEnd:   [{matcher:"", hooks:[{type:"command", command:$end,   timeout:10}]}],
        PreCompact:   [{matcher:"", hooks:[{type:"command", command:$compact, timeout:10}]}]
      }
    }'
}

codex_hooks_payload() {
  jq -n \
    --arg start "uv run --project .wiki python $HOOK_SESSION_START_REL" \
    --arg end "uv run --project .wiki python $HOOK_SESSION_END_REL" \
    '{
      hooks: {
        SessionStart: [{matcher:"", hooks:[{type:"command", command:$start, timeout:15}]}],
        Stop:         [{matcher:"", hooks:[{type:"command", command:$end,   timeout:10}]}]
      }
    }'
}

gemini_hooks_payload() {
  # Gemini timeouts are in milliseconds.
  jq -n \
    --arg start "uv run --project .wiki python $HOOK_SESSION_START_REL" \
    --arg end "uv run --project .wiki python $HOOK_SESSION_END_REL" \
    --arg compact "uv run --project .wiki python $HOOK_PRE_COMPACT_REL" \
    '{
      hooks: {
        SessionStart: [{matcher:"", hooks:[{type:"command", command:$start, timeout:15000}]}],
        SessionEnd:   [{matcher:"", hooks:[{type:"command", command:$end,   timeout:10000}]}],
        PreCompress:  [{matcher:"", hooks:[{type:"command", command:$compact, timeout:10000}]}]
      }
    }'
}

cursor_hooks_payload() {
  # Cursor 1.7+ supports the full lifecycle: sessionStart, sessionEnd, preCompact.
  # Schema reference: https://cursor.com/docs/hooks (camelCase event names,
  # version=1, hooks dict with arrays per event, no `matcher` wrapper —
  # commands attach directly to the event array).
  jq -n \
    --arg start "uv run --project .wiki python $HOOK_SESSION_START_REL" \
    --arg end "uv run --project .wiki python $HOOK_SESSION_END_REL" \
    --arg compact "uv run --project .wiki python $HOOK_PRE_COMPACT_REL" \
    '{
      version: 1,
      hooks: {
        sessionStart: [{type:"command", command:$start,   timeout:15}],
        sessionEnd:   [{type:"command", command:$end,     timeout:10}],
        preCompact:   [{type:"command", command:$compact, timeout:10}]
      }
    }'
}

agent_payload() {
  case "$1" in
    claude) claude_hooks_payload ;;
    codex)  codex_hooks_payload ;;
    gemini) gemini_hooks_payload ;;
    cursor) cursor_hooks_payload ;;
    *) return 1 ;;
  esac
}

# ── Merge / install / uninstall ──────────────────────────────────────
# Merge a JSON payload into an existing JSON file using jq deep-merge.
merge_into_config() {
  local cfg="$1" payload="$2"
  mkdir -p "$(dirname "$cfg")"
  if [[ -f "$cfg" ]]; then
    if ! jq . "$cfg" >/dev/null 2>&1; then
      err "Existing $cfg is not valid JSON — refusing to merge."
      return 1
    fi
    jq --argjson p "$payload" '. * $p' "$cfg" > "$cfg.tmp" && mv "$cfg.tmp" "$cfg"
  else
    echo "$payload" | jq . > "$cfg"
  fi
}

install_one() {
  local agent="$1" scope="$2"
  local cfg; cfg="$(agent_config_path "$agent" "$scope")"
  local payload; payload="$(agent_payload "$agent")" || { err "unknown agent: $agent"; return 1; }
  local bak=""
  [[ -f "$cfg" ]] && bak="$(backup_file "$cfg")"
  if merge_into_config "$cfg" "$payload"; then
    if [[ -n "$bak" ]]; then
      ok "$agent ($scope): updated $cfg ${C_DIM}(backup: $bak)${C_RESET}"
    else
      ok "$agent ($scope): created $cfg"
    fi
  else
    err "$agent ($scope): merge failed"
    return 1
  fi
}

uninstall_one() {
  local agent="$1" scope="$2"
  local cfg; cfg="$(agent_config_path "$agent" "$scope")"
  if [[ ! -f "$cfg" ]]; then
    warn "$agent ($scope): no config at $cfg — skipping"
    return 0
  fi
  local bak; bak="$(backup_file "$cfg")"
  jq '
    if .hooks then
      .hooks |= with_entries(
        .value |= (
          if type == "array" then
            map(
              if (.hooks | type) == "array"
              then .hooks |= map(select((.command // "") | test("\\.wiki/hooks/") | not))
              else .
              end
            )
            | map(select((.hooks // []) | length > 0))
          elif type == "object" then
            if (.command // "" | test("\\.wiki/hooks/")) then empty else . end
          else .
          end
        )
      )
    else . end
  ' "$cfg" > "$cfg.tmp" && mv "$cfg.tmp" "$cfg"
  ok "$agent ($scope): removed wiki hooks ${C_DIM}(backup: $bak)${C_RESET}"
}
