# shellcheck shell=bash
# skills.sh — interactive flows for `wiki skills {install,uninstall,sync,status}`.
# Engine ships its skills at .wiki/skills/<name>/ and symlinks them into
# <vault>/.claude/skills/<name>/ so Claude Code discovers them. Only symlinks
# pointing at ../../.wiki/skills/<name> are owned by the engine; foreign
# entries (user-authored skills, other tools' symlinks) are never touched.

[[ -n "${__WIKI_SKILLS_LOADED:-}" ]] && return 0
__WIKI_SKILLS_LOADED=1

SKILLS_SRC_DIR="$WIKI_DIR/skills"
SKILLS_DST_DIR="$ROOT_DIR/.claude/skills"
SKILLS_LINK_TARGET_PREFIX="../../.wiki/skills"

# True iff $1 is a symlink pointing into the engine's skills dir.
_skill_is_engine_owned() {
  local link="$1"
  [[ -L "$link" ]] || return 1
  local target; target="$(readlink "$link")"
  [[ "$target" == "$SKILLS_LINK_TARGET_PREFIX/"* ]]
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

# Used by `wiki update` after `git pull` — install new + prune stale, single-line summary.
skills_cmd_sync() {
  skills_install_silent
  skills_prune_stale_silent
  local added="$_skills_install_count_added"
  local pruned="$_skills_prune_count"
  local foreign="$_skills_install_count_foreign"
  if (( added == 0 && pruned == 0 && foreign == 0 )); then
    info "skills: up to date"
  else
    local msg="skills:"
    (( added > 0 )) && msg+=" +$added linked"
    (( pruned > 0 )) && msg+=" -$pruned pruned"
    (( foreign > 0 )) && msg+=" $foreign collision(s)"
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
}
