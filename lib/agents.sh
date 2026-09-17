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

# All payload generators emit a `cd '<abs-vault>/.wiki' && uv run python
# hooks/<name>.py` form. The cd anchors CWD inside the engine; uv then
# auto-discovers pyproject.toml in CWD (no --project flag needed) and the
# script path stays relative + readable. Works for both user-scope and
# project-scope: user-scope sessions launched from arbitrary repos still
# resolve correctly because the cd is absolute.
# Single quotes around the path survive into the JSON command string and
# protect paths that contain spaces (e.g. Mobile Documents/iCloud~md~obsidian).
#
# When the engine environment lives outside the vault (WIKI_VENV_DIR from
# lib/common.sh — cloud-synced vaults), the command carries
# `UV_PROJECT_ENVIRONMENT='<dir>'` literally: the hook process is spawned by
# the agent with the agent's env, not by `wiki`, so nothing else could set
# it, and everything the hook spawns (flush → compile → piggybacks) inherits
# it. `wiki doctor` (hooks-installed) warns when installed hooks lack it.
hook_cmd() {
  local script="$1" env_prefix=""
  if [[ -n "${WIKI_VENV_DIR:-}" ]]; then
    env_prefix="UV_PROJECT_ENVIRONMENT='$WIKI_VENV_DIR' "
  fi
  printf "cd '%s' && %suv run python %s" "$WIKI_DIR" "$env_prefix" "$script"
}

claude_hooks_payload() {
  jq -n \
    --arg start "$(hook_cmd hooks/session-start.py)" \
    --arg end "$(hook_cmd hooks/session-end.py)" \
    --arg compact "$(hook_cmd hooks/pre-compact.py)" \
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
    --arg start "$(hook_cmd hooks/session-start.py)" \
    --arg end "$(hook_cmd hooks/session-end.py)" \
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
    --arg start "$(hook_cmd hooks/session-start.py)" \
    --arg end "$(hook_cmd hooks/session-end.py)" \
    --arg compact "$(hook_cmd hooks/pre-compact.py)" \
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
    --arg start "$(hook_cmd hooks/session-start.py)" \
    --arg end "$(hook_cmd hooks/session-end.py)" \
    --arg compact "$(hook_cmd hooks/pre-compact.py)" \
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
# Merge a JSON payload into an existing JSON file.
#
# Top-level keys deep-merge (jq `*`). The `hooks` block does NOT: jq's `*`
# REPLACES arrays, so a plain deep-merge of `{hooks:{SessionStart:[wiki]}}`
# into a config whose SessionStart already holds the operator's other hooks
# would silently drop those (lxw 2026-09-17: one foreign entry per agent
# in SessionStart — ytstack / herdr — gone on the next `wiki hooks install`).
# Per event we therefore keep every entry that is not wiki-managed and
# replace only ours (identified by the same command grammar as
# `hooks_installed`); both entry shapes are handled — Claude/Codex/Gemini
# `{matcher, hooks:[{command}]}` and Cursor's bare `{type, command}`.
_WIKI_HOOK_CMD_RE='\.wiki['"'"'"/ ].*hooks/(session-(start|end)|pre-compact)'

merge_into_config() {
  local cfg="$1" payload="$2"
  mkdir -p "$(dirname "$cfg")"
  if [[ -f "$cfg" ]]; then
    if ! jq . "$cfg" >/dev/null 2>&1; then
      err "Existing $cfg is not valid JSON — refusing to merge."
      return 1
    fi
    jq --argjson p "$payload" --arg re "$_WIKI_HOOK_CMD_RE" '
      def wiki_managed:
        ([.command? // empty] + [((.hooks // [])[]? | .command? // empty)])
        | any(test($re));
      . as $cfg
      | ($cfg * ($p | del(.hooks)))
      | if ($p.hooks // null) then
          .hooks = (
            reduce ($p.hooks | to_entries[]) as $e ($cfg.hooks // {};
              .[$e.key] = (((.[$e.key] // []) | map(select(wiki_managed | not))) + $e.value))
          )
        else . end
    ' "$cfg" > "$cfg.tmp" && mv "$cfg.tmp" "$cfg"
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
