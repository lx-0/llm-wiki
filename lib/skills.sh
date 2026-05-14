# shellcheck shell=bash
# skills.sh — interactive flows for `wiki skills {install,uninstall,sync,status}`.
# Engine ships its skills at .wiki/skills/<name>/ and symlinks them into
# <vault>/.claude/skills/<name>/ so Claude Code discovers them. Only symlinks
# pointing at ../../.wiki/skills/<name> are owned by the engine; foreign
# entries (user-authored skills, other tools' symlinks) are never touched.
#
# Global install: a few skills are global-eligible (GLOBAL_SKILLS) — they let
# an agent in *any* project discover and use a locally-available wiki. When
# `skills.global_install` is enabled, those are also linked into
# ~/.claude/skills/ and the vault is recorded in ~/.config/llm-wiki/vaults so
# the skill's discovery probe can find it.

[[ -n "${__WIKI_SKILLS_LOADED:-}" ]] && return 0
__WIKI_SKILLS_LOADED=1

SKILLS_SRC_DIR="$WIKI_DIR/skills"
SKILLS_DST_DIR="$ROOT_DIR/.claude/skills"
SKILLS_LINK_TARGET_PREFIX="../../.wiki/skills"

# Global-install constants. GLOBAL_SKILLS is the allowlist of skills safe to
# link outside a vault — keep it tight; the others operate *inside* a vault.
GLOBAL_SKILLS=(use-llm-wiki)
GLOBAL_SKILLS_DST="$HOME/.claude/skills"
REGISTRY_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/llm-wiki"
REGISTRY_FILE="$REGISTRY_DIR/vaults"

# True iff $1 is a symlink pointing into the engine's skills dir.
_skill_is_engine_owned() {
  local link="$1"
  [[ -L "$link" ]] || return 1
  local target; target="$(readlink "$link")"
  [[ "$target" == "$SKILLS_LINK_TARGET_PREFIX/"* ]]
}

# True iff `skills.global_install` is enabled in config.yaml. config_get is
# defined in lib/config.sh (sourced by `wiki` after this file — fine: this is
# only ever called at runtime, by which point every lib is loaded).
_skills_global_enabled() {
  [[ "$(config_get skills.global_install 2>/dev/null)" == "True" ]]
}

# Install missing engine-skill symlinks. Idempotent: existing engine-owned links
# are left alone; existing foreign entries (regular dirs, other symlinks) are
# left alone and reported. Returns count via globals (caller prints).
_skills_install_count_added=0
_skills_install_count_skipped=0
_skills_install_count_foreign=0
skills_install_silent() {
  _skills_install_count_added=0
  _skills_install_count_skipped=0
  _skills_install_count_foreign=0
  [[ -d "$SKILLS_SRC_DIR" ]] || return 0
  mkdir -p "$SKILLS_DST_DIR"
  local skill_path name target_link
  for skill_path in "$SKILLS_SRC_DIR"/*/; do
    [[ -d "$skill_path" ]] || continue
    name=$(basename "$skill_path")
    target_link="$SKILLS_DST_DIR/$name"
    if _skill_is_engine_owned "$target_link"; then
      _skills_install_count_skipped=$((_skills_install_count_skipped + 1))
      continue
    fi
    if [[ -L "$target_link" || -e "$target_link" ]]; then
      _skills_install_count_foreign=$((_skills_install_count_foreign + 1))
      continue
    fi
    ln -s "$SKILLS_LINK_TARGET_PREFIX/$name" "$target_link"
    _skills_install_count_added=$((_skills_install_count_added + 1))
  done
}

# Remove stale engine-owned symlinks whose source skill no longer exists in
# .wiki/skills/. Used by `skills sync` after an update; never touches foreign
# entries. Returns count via globals.
_skills_prune_count=0
skills_prune_stale_silent() {
  _skills_prune_count=0
  [[ -d "$SKILLS_DST_DIR" ]] || return 0
  local link name target src_path
  for link in "$SKILLS_DST_DIR"/*; do
    [[ -L "$link" ]] || continue
    _skill_is_engine_owned "$link" || continue
    name=$(basename "$link")
    src_path="$SKILLS_SRC_DIR/$name"
    if [[ ! -d "$src_path" ]]; then
      rm -- "$link"
      _skills_prune_count=$((_skills_prune_count + 1))
    fi
  done
}

# ── Global install: registry + symlink helpers ─────────────────────────
# The registry is a plain newline-delimited file of absolute vault-root paths.
# It is the cross-vault source of truth the discovery probe reads; each vault
# adds/removes only its own line. Writes fail soft — a missing global symlink
# is recoverable, a hard error on `wiki update` is not.
_registry_add() {
  mkdir -p "$REGISTRY_DIR" 2>/dev/null || { warn "cannot create $REGISTRY_DIR — vault not registered"; return 0; }
  touch "$REGISTRY_FILE" 2>/dev/null   || { warn "cannot write $REGISTRY_FILE — vault not registered"; return 0; }
  grep -qxF "$ROOT_DIR" "$REGISTRY_FILE" 2>/dev/null || printf '%s\n' "$ROOT_DIR" >> "$REGISTRY_FILE"
}

_registry_remove() {
  [[ -f "$REGISTRY_FILE" ]] || return 0
  local tmp; tmp="$(mktemp)" || return 0
  grep -vxF "$ROOT_DIR" "$REGISTRY_FILE" > "$tmp" 2>/dev/null || true
  mv "$tmp" "$REGISTRY_FILE" 2>/dev/null || rm -f "$tmp"
}

# Link GLOBAL_SKILLS into ~/.claude/skills/ with an *absolute* target (relative
# targets don't resolve from ~/.claude/). A pre-existing link into *any*
# .wiki/skills/ is engine-owned and left alone — the SKILL.md is engine-
# identical across vaults and discovery is registry-driven, so "points at
# another vault" is not a collision. Only genuinely foreign entries are
# reported. Counts via globals; also registers the vault.
_skills_global_added=0
_skills_global_skipped=0
_skills_global_foreign=0
skills_install_global_silent() {
  _skills_global_added=0
  _skills_global_skipped=0
  _skills_global_foreign=0
  [[ -d "$SKILLS_SRC_DIR" ]] || return 0
  mkdir -p "$GLOBAL_SKILLS_DST"
  local name link target cur
  for name in "${GLOBAL_SKILLS[@]}"; do
    [[ -d "$SKILLS_SRC_DIR/$name" ]] || continue
    link="$GLOBAL_SKILLS_DST/$name"
    target="$SKILLS_SRC_DIR/$name"
    if [[ -L "$link" ]]; then
      cur="$(readlink "$link")"
      if [[ "$cur" == "$target" || "$cur" == */.wiki/skills/* ]]; then
        _skills_global_skipped=$((_skills_global_skipped + 1))
      else
        _skills_global_foreign=$((_skills_global_foreign + 1))
      fi
      continue
    fi
    if [[ -e "$link" ]]; then
      _skills_global_foreign=$((_skills_global_foreign + 1))
      continue
    fi
    ln -s "$target" "$link"
    _skills_global_added=$((_skills_global_added + 1))
  done
  _registry_add
}

# Remove global symlinks that point into *this* vault's .wiki/skills/, and
# deregister this vault. Other vaults' global links and foreign entries are
# left untouched. Count via global.
_skills_global_removed=0
skills_uninstall_global() {
  _skills_global_removed=0
  if [[ -d "$GLOBAL_SKILLS_DST" ]]; then
    local name link
    for name in "${GLOBAL_SKILLS[@]}"; do
      link="$GLOBAL_SKILLS_DST/$name"
      [[ -L "$link" ]] || continue
      [[ "$(readlink "$link")" == "$SKILLS_SRC_DIR/$name" ]] || continue
      rm -- "$link"
      _skills_global_removed=$((_skills_global_removed + 1))
    done
  fi
  _registry_remove
}

# ── User-facing subcommands ────────────────────────────────────────────
skills_cmd_install() {
  banner "wiki skills install" "Symlink engine skills into .claude/skills/"
  skills_install_silent
  if (( _skills_install_count_added > 0 )); then
    ok "linked $_skills_install_count_added skill(s) into $SKILLS_DST_DIR"
  fi
  if (( _skills_install_count_skipped > 0 )); then
    info "$_skills_install_count_skipped skill(s) already linked"
  fi
  if (( _skills_install_count_foreign > 0 )); then
    warn "$_skills_install_count_foreign name(s) collide with non-engine entries — left untouched"
    info "Run 'wiki skills status' to see which."
  fi
  if (( _skills_install_count_added + _skills_install_count_skipped + _skills_install_count_foreign == 0 )); then
    info "no skills found in $SKILLS_SRC_DIR — nothing to do"
  fi
  # Global-eligible skills, when opted in via `skills.global_install`.
  if _skills_global_enabled; then
    echo
    skills_install_global_silent
    info "global install (skills.global_install: true)"
    (( _skills_global_added > 0 ))   && ok   "linked $_skills_global_added skill(s) into $GLOBAL_SKILLS_DST"
    (( _skills_global_skipped > 0 )) && info "$_skills_global_skipped global skill(s) already linked"
    (( _skills_global_foreign > 0 )) && warn "$_skills_global_foreign global name(s) collide with non-engine entries — left untouched"
    info "vault registered in $REGISTRY_FILE"
  fi
}

skills_cmd_uninstall() {
  banner "wiki skills uninstall" "Remove engine-owned symlinks only"
  [[ -d "$SKILLS_DST_DIR" ]] || { info "no $SKILLS_DST_DIR — nothing to do"; return 0; }
  local link removed=0
  for link in "$SKILLS_DST_DIR"/*; do
    _skill_is_engine_owned "$link" || continue
    rm -- "$link"
    removed=$((removed + 1))
  done
  if (( removed > 0 )); then
    ok "removed $removed engine-owned symlink(s)"
  else
    info "no engine-owned symlinks found"
  fi
}

# Used by `wiki update` after `git pull` — install new + prune stale, single-line
# summary. When `skills.global_install` is on, also refreshes the global links
# and re-registers the vault — so an opted-in vault stays globally linked across
# updates with no re-flagging (the config key is the durable opt-in).
skills_cmd_sync() {
  skills_install_silent
  skills_prune_stale_silent
  local added="$_skills_install_count_added"
  local pruned="$_skills_prune_count"
  local foreign="$_skills_install_count_foreign"
  local global_added=0
  if _skills_global_enabled; then
    skills_install_global_silent
    global_added="$_skills_global_added"
  fi
  if (( added == 0 && pruned == 0 && foreign == 0 && global_added == 0 )); then
    info "skills: up to date"
  else
    local msg="skills:"
    (( added > 0 )) && msg+=" +$added linked"
    (( pruned > 0 )) && msg+=" -$pruned pruned"
    (( foreign > 0 )) && msg+=" $foreign collision(s)"
    (( global_added > 0 )) && msg+=" +$global_added global"
    ok "$msg"
  fi
}

skills_cmd_status() {
  banner "wiki skills status"
  printf "%-32s %s\n" "SKILL" "STATE"
  printf "%s\n" "──────────────────────────────────────────────────────────────"
  local skill_path name target_link state
  if [[ -d "$SKILLS_SRC_DIR" ]]; then
    for skill_path in "$SKILLS_SRC_DIR"/*/; do
      [[ -d "$skill_path" ]] || continue
      name=$(basename "$skill_path")
      target_link="$SKILLS_DST_DIR/$name"
      if _skill_is_engine_owned "$target_link"; then
        state="${C_GREEN}linked${C_RESET}"
      elif [[ -L "$target_link" || -e "$target_link" ]]; then
        state="${C_YELLOW}collision${C_RESET} (foreign entry — not managed)"
      else
        state="${C_DIM}missing${C_RESET}"
      fi
      printf "%-32s %s\n" "$name" "$state"
    done
  else
    info "no $SKILLS_SRC_DIR directory"
    return 0
  fi
  # Stale check: engine-owned links whose source vanished
  if [[ -d "$SKILLS_DST_DIR" ]]; then
    local link any_stale=0
    for link in "$SKILLS_DST_DIR"/*; do
      _skill_is_engine_owned "$link" || continue
      name=$(basename "$link")
      [[ -d "$SKILLS_SRC_DIR/$name" ]] && continue
      if (( any_stale == 0 )); then
        echo
        warn "stale engine-owned symlinks (source no longer exists):"
        any_stale=1
      fi
      printf "  %s\n" "$name"
    done
    (( any_stale == 1 )) && info "Run 'wiki skills sync' to prune them."
  fi

  # ── Global install ──────────────────────────────────────────────────
  echo
  local global_on; global_on="$(config_get skills.global_install 2>/dev/null || echo '?')"
  if [[ "$global_on" == "True" ]]; then
    printf "%-32s %s\n" "GLOBAL INSTALL" "${C_GREEN}on${C_RESET}  (skills.global_install)"
  else
    printf "%-32s %s\n" "GLOBAL INSTALL" "${C_DIM}off${C_RESET} (skills.global_install — wiki skills install --global)"
  fi
  local gname glink gcur gstate
  for gname in "${GLOBAL_SKILLS[@]}"; do
    glink="$GLOBAL_SKILLS_DST/$gname"
    if [[ -L "$glink" ]]; then
      gcur="$(readlink "$glink")"
      if [[ "$gcur" == "$SKILLS_SRC_DIR/$gname" ]]; then
        gstate="${C_GREEN}linked${C_RESET} → this vault"
      elif [[ "$gcur" == */.wiki/skills/* ]]; then
        gstate="${C_YELLOW}linked${C_RESET} → other vault ($gcur)"
      else
        gstate="${C_YELLOW}collision${C_RESET} (foreign entry — not managed)"
      fi
    elif [[ -e "$glink" ]]; then
      gstate="${C_YELLOW}collision${C_RESET} (foreign entry — not managed)"
    else
      gstate="${C_DIM}not linked${C_RESET}"
    fi
    printf "  %-30s %s\n" "$gname" "$gstate"
  done
  if [[ -f "$REGISTRY_FILE" ]]; then
    printf "  %-30s %s\n" "registry" "$REGISTRY_FILE"
    local v
    while IFS= read -r v; do
      [[ -n "$v" ]] || continue
      if [[ -x "$v/.wiki/wiki" ]]; then
        printf "    %s%s%s %s\n" "$C_GREEN" "✓" "$C_RESET" "$v"
      else
        printf "    %s%s%s %s %s(stale — no .wiki/wiki)%s\n" "$C_YELLOW" "!" "$C_RESET" "$v" "$C_DIM" "$C_RESET"
      fi
    done < "$REGISTRY_FILE"
  else
    printf "  %-30s %s%s%s\n" "registry" "$C_DIM" "none ($REGISTRY_FILE)" "$C_RESET"
  fi
}
