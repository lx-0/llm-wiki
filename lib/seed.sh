#!/usr/bin/env bash
# lib/seed.sh — vault-template seeding logic shared by install.sh and `wiki seed`.
#
# Required helpers (loaded by both callers): ok, info, warn, err.
# Required tools: jq (for community-plugins.json merge).

# Guard against double-source.
[[ -n "${__WIKI_SEED_LOADED:-}" ]] && return 0
__WIKI_SEED_LOADED=1


# ── Internal: copy if absent / overwrite if --force ────────────────
# Modes:
#   force=0 check=0   normal seed: copy when missing, keep + report drift if exists
#   force=1           overwrite: copy unconditionally (destructive)
#   check=1           read-only: report state (missing/drifted/up-to-date); never writes
_seed_file() {
  local src="$1" dst="$2" force="$3" label="${4:-}" check="${5:-0}"
  [[ -z "$label" ]] && label="$(basename "$dst")"
  if [[ ! -f "$src" ]]; then
    return 0  # template missing — silently skip
  fi

  if [[ "$check" == "1" ]]; then
    if [[ ! -f "$dst" ]]; then
      warn "missing $label (run \`wiki seed\` to install)"
    elif cmp -s "$src" "$dst"; then
      ok "up-to-date $label"
    else
      info "drifted $label (engine template differs; \`wiki seed --force\` overwrites)"
    fi
    return 0
  fi

  if [[ ! -f "$dst" ]]; then
    mkdir -p "$(dirname "$dst")"
    cp "$src" "$dst"
    ok "seeded $label"
    return 0
  fi
  if [[ "$force" == "1" ]]; then
    mkdir -p "$(dirname "$dst")"
    cp "$src" "$dst"
    ok "overwrote $label (--force)"
    return 0
  fi
  if cmp -s "$src" "$dst"; then
    info "kept existing $label (up-to-date)"
  else
    info "kept existing $label (drifted from engine; rerun with --force to overwrite, or \`wiki seed --check\` to audit)"
  fi
}


# ── Internal: merge community-plugins.json (additive union) ────────
# This is always safe — we only ADD missing engine plugins to the list,
# never remove operator-added entries. Idempotent. check=1 reports
# pending merges without writing.
_merge_community_plugins() {
  local src="$1" dst="$2" check="${3:-0}"
  if [[ ! -f "$src" ]]; then
    return 0
  fi
  if [[ ! -f "$dst" ]]; then
    if [[ "$check" == "1" ]]; then
      warn "missing community-plugins.json"
      return 0
    fi
    mkdir -p "$(dirname "$dst")"
    cp "$src" "$dst"
    ok "seeded community-plugins.json"
    return 0
  fi
  if ! command -v jq >/dev/null 2>&1; then
    warn "jq not available — skipping community-plugins.json merge"
    return 0
  fi
  local before after merged
  before="$(jq -r 'length' "$dst" 2>/dev/null || echo 0)"
  merged="$(jq -s '.[0] + .[1] | unique' "$dst" "$src" 2>/dev/null || echo '')"
  if [[ -z "$merged" ]]; then
    warn "community-plugins.json — merge failed (malformed JSON?)"
    return 0
  fi
  after="$(printf '%s\n' "$merged" | jq -r 'length')"
  if [[ "$check" == "1" ]]; then
    if [[ "$before" != "$after" ]]; then
      info "drifted community-plugins.json ($before installed; engine ships $after — would merge to $after)"
    else
      ok "up-to-date community-plugins.json"
    fi
    return 0
  fi
  printf '%s\n' "$merged" > "$dst.tmp" && mv "$dst.tmp" "$dst"
  if [[ "$before" != "$after" ]]; then
    ok "community-plugins.json — merged ($before → $after entries)"
  else
    info "community-plugins.json — already up to date"
  fi
}


# ── Internal: merge appearance.json (additive enabledCssSnippets union) ──
# Preserve operator-set fields (cssTheme, theme, baseFontSize, etc.) and only
# union the enabledCssSnippets list. Without this, our CSS snippet sits in
# .obsidian/snippets/ but is never enabled by Obsidian — the dashboard layout
# silently fails.
_merge_appearance_json() {
  local src="$1" dst="$2" check="${3:-0}"
  if [[ ! -f "$src" ]]; then
    return 0
  fi
  if [[ ! -f "$dst" ]]; then
    if [[ "$check" == "1" ]]; then
      warn "missing appearance.json"
      return 0
    fi
    mkdir -p "$(dirname "$dst")"
    cp "$src" "$dst"
    ok "seeded appearance.json"
    return 0
  fi
  if ! command -v jq >/dev/null 2>&1; then
    warn "jq not available — skipping appearance.json merge"
    return 0
  fi
  local before merged after
  before="$(jq -r '(.enabledCssSnippets // []) | join(",")' "$dst" 2>/dev/null || echo '')"
  merged="$(jq -s '
    .[0] as $cur | .[1] as $eng |
    $cur + {
      enabledCssSnippets: (((($cur.enabledCssSnippets // []) + ($eng.enabledCssSnippets // [])) | unique))
    }
  ' "$dst" "$src" 2>/dev/null || echo '')"
  if [[ -z "$merged" ]]; then
    warn "appearance.json — merge failed (malformed JSON?)"
    return 0
  fi
  after="$(printf '%s\n' "$merged" | jq -r '(.enabledCssSnippets // []) | join(",")')"
  if [[ "$check" == "1" ]]; then
    if [[ "$before" != "$after" ]]; then
      info "drifted appearance.json (enabledCssSnippets [$before] → would merge to [$after])"
    else
      ok "up-to-date appearance.json"
    fi
    return 0
  fi
  printf '%s\n' "$merged" > "$dst.tmp" && mv "$dst.tmp" "$dst"
  if [[ "$before" != "$after" ]]; then
    ok "appearance.json — enabledCssSnippets [$before] → [$after]"
  else
    info "appearance.json — enabledCssSnippets already up to date"
  fi
}


# ── Internal: merge meta-bind data.json (buttonTemplates union by id) ──
# Engine ships canonical button templates referenced from dashboard.md as
# `BUTTON[btn-*]`. In Meta-Bind v1.4.x, IDs are resolved against the plugin's
# buttonTemplates registry — buttons defined in transcluded .md files no
# longer leak across files. We merge so operator's other settings (devMode,
# preferredDateFormat, firstWeekday, ...) and any user-added buttonTemplates
# with non-conflicting ids are preserved. Engine ids overwrite same-id user
# entries (engine is canonical for those).
_merge_meta_bind_data() {
  local src="$1" dst="$2" check="${3:-0}"
  if [[ ! -f "$src" ]]; then
    return 0
  fi
  if [[ ! -f "$dst" ]]; then
    if [[ "$check" == "1" ]]; then
      warn "missing obsidian-meta-bind-plugin/data.json"
      return 0
    fi
    mkdir -p "$(dirname "$dst")"
    cp "$src" "$dst"
    ok "seeded obsidian-meta-bind-plugin/data.json"
    return 0
  fi
  if ! command -v jq >/dev/null 2>&1; then
    warn "jq not available — skipping obsidian-meta-bind-plugin/data.json merge"
    return 0
  fi
  local before merged after
  before="$(jq -r '(.buttonTemplates // []) | map(.id) | join(",")' "$dst" 2>/dev/null || echo '')"
  merged="$(jq -s '
    .[0] as $cur | .[1] as $eng |
    ($eng.buttonTemplates // []) as $eb |
    ($eb | map(.id)) as $eids |
    $cur + {
      buttonTemplates: (
        $eb +
        (($cur.buttonTemplates // []) | map(select(.id as $id | $eids | index($id) | not)))
      )
    }
  ' "$dst" "$src" 2>/dev/null || echo '')"
  if [[ -z "$merged" ]]; then
    warn "obsidian-meta-bind-plugin/data.json — merge failed (malformed JSON?)"
    return 0
  fi
  after="$(printf '%s\n' "$merged" | jq -r '(.buttonTemplates // []) | map(.id) | join(",")')"
  if [[ "$check" == "1" ]]; then
    if [[ "$before" != "$after" ]]; then
      info "drifted obsidian-meta-bind-plugin/data.json (buttonTemplates [$before] → would merge to [$after])"
    else
      ok "up-to-date obsidian-meta-bind-plugin/data.json"
    fi
    return 0
  fi
  printf '%s\n' "$merged" > "$dst.tmp" && mv "$dst.tmp" "$dst"
  if [[ "$before" != "$after" ]]; then
    ok "obsidian-meta-bind-plugin/data.json — buttonTemplates [$before] → [$after]"
  else
    info "obsidian-meta-bind-plugin/data.json — buttonTemplates already up to date"
  fi
}


# ── Internal: merge agent-task buttons into shell-commands data.json ──
# For every prompts/agents/*.md declaring a `button:` block, ensure a matching
# entry exists in <vault>/.obsidian/plugins/obsidian-shellcommands/data.json
# under the spec's shell_command_id. Additive merge — operator's other shell
# commands are preserved, never modified. Idempotent.
_merge_agent_shell_commands() {
  local target="$1" wiki_dir="$2"
  local data="$target/.obsidian/plugins/obsidian-shellcommands/data.json"
  if [[ ! -f "$data" ]]; then
    return 0  # base seed didn't run yet; nothing to merge into
  fi
  if ! command -v jq >/dev/null 2>&1; then
    warn "jq not available — skipping agent shell-commands merge"
    return 0
  fi
  local entries
  entries="$(uv run --quiet --project "$wiki_dir" python "$wiki_dir/scripts/dashboard/agent_buttons.py" shell-commands 2>/dev/null || echo '{}')"
  if [[ -z "$entries" ]] || [[ "$entries" == "{}" ]]; then
    return 0
  fi
  local before after merged
  before="$(jq -r '.shell_commands | keys | length' "$data" 2>/dev/null || echo 0)"
  merged="$(jq --argjson agents "$entries" '
    .shell_commands = (.shell_commands + ($agents | with_entries(select(.key as $k | (input_filename | "ignored") and ($k | tostring)))))
    | .shell_commands = (.shell_commands + $agents)
  ' "$data" 2>/dev/null || echo '')"
  if [[ -z "$merged" ]]; then
    warn "agent shell-commands merge failed"
    return 0
  fi
  printf '%s\n' "$merged" > "$data.tmp" && mv "$data.tmp" "$data"
  after="$(jq -r '.shell_commands | keys | length' "$data")"
  if [[ "$before" != "$after" ]]; then
    ok "agent shell-commands — $before → $after entries"
  else
    info "agent shell-commands — already up to date"
  fi
}


# ── Internal: rewrite the agent-buttons regions in dashboard.md ────────
# Replaces the inline-refs region and the hidden-defs region from the
# discovered agent specs. Marker-based, idempotent, surgical (nothing
# outside the markers is touched).
_rewrite_dashboard_agent_buttons() {
  local target="$1" wiki_dir="$2"
  local dashboard="$target/dashboard.md"
  if [[ ! -f "$dashboard" ]]; then
    return 0
  fi
  local result
  result="$(uv run --quiet --project "$wiki_dir" python "$wiki_dir/scripts/dashboard/agent_buttons.py" update-dashboard "$dashboard" 2>&1 || echo unchanged)"
  if [[ "$result" == "changed" ]]; then
    ok "dashboard.md — agent-buttons regions refreshed"
  else
    info "dashboard.md — agent-buttons already up to date"
  fi
}


# ── Public: seed all vault templates ───────────────────────────────
# Args: <target-vault-root> <wiki-dir> [force=0|1] [check=0|1]
# check=1 reports drift without writing anything (read-only audit).
seed_vault_templates() {
  local target="$1" wiki_dir="$2" force="${3:-0}" check="${4:-0}"
  local templates_dir="$wiki_dir/templates"

  if [[ ! -d "$templates_dir" ]]; then
    warn "no templates dir at $templates_dir"
    return 1
  fi

  # 1. README.md — vault-owner-facing quickstart.
  _seed_file "$templates_dir/README.md" "$target/README.md" "$force" "README.md" "$check"

  # 2. AGENTS.md — article-schema spec read by every compile prompt.
  _seed_file "$templates_dir/AGENTS.example.md" "$target/AGENTS.md" "$force" "AGENTS.md" "$check"

  # 3. dashboard.md — Obsidian Homepage target.
  _seed_file "$templates_dir/dashboard.md" "$target/dashboard.md" "$force" "dashboard.md" "$check"

  # 3b. knowledge.base — native Obsidian Bases knowledge browser (built-in 1.10+).
  _seed_file "$templates_dir/knowledge.base" "$target/knowledge.base" "$force" "knowledge.base" "$check"

  # 4. Cache files (_dashboard-*.md) are NOT seeded — they're producer-only outputs
  #    of dashboard_stats.py / dashboard_lint.py. Seeding them (especially with --force)
  #    would clobber live data with the placeholder template. First wiki flush writes
  #    them fresh. See M003-S07 for full rationale.

  # 5. Templates/*.md — typed-note templates consumed by QuickAdd.
  if [[ -d "$templates_dir/Templates" ]]; then
    local tpl
    for tpl in "$templates_dir/Templates"/*.md; do
      [[ -f "$tpl" ]] || continue
      _seed_file "$tpl" "$target/Templates/$(basename "$tpl")" "$force" "Templates/$(basename "$tpl")" "$check"
    done
  fi

  # 5b. knowledge/MOCs/*.md — Map-of-Content stubs.
  if [[ -d "$templates_dir/knowledge/MOCs" ]]; then
    local moc
    for moc in "$templates_dir/knowledge/MOCs"/*.md; do
      [[ -f "$moc" ]] || continue
      _seed_file "$moc" "$target/knowledge/MOCs/$(basename "$moc")" "$force" "knowledge/MOCs/$(basename "$moc")" "$check"
    done
  fi

  # 6. .obsidian/*.json — top-level configs.
  if [[ -d "$templates_dir/.obsidian" ]]; then
    [[ "$check" == "1" ]] || mkdir -p "$target/.obsidian"
    local f base
    for f in "$templates_dir/.obsidian"/*.json; do
      [[ -f "$f" ]] || continue
      base="$(basename "$f")"
      if [[ "$base" == "community-plugins.json" ]]; then
        _merge_community_plugins "$f" "$target/.obsidian/$base" "$check"
      elif [[ "$base" == "appearance.json" ]]; then
        _merge_appearance_json "$f" "$target/.obsidian/$base" "$check"
      else
        _seed_file "$f" "$target/.obsidian/$base" "$force" ".obsidian/$base" "$check"
      fi
    done

    # 7. .obsidian/snippets/*.css — CSS snippets for the dashboard layout.
    if [[ -d "$templates_dir/.obsidian/snippets" ]]; then
      [[ "$check" == "1" ]] || mkdir -p "$target/.obsidian/snippets"
      local css
      for css in "$templates_dir/.obsidian/snippets"/*.css; do
        [[ -f "$css" ]] || continue
        _seed_file "$css" "$target/.obsidian/snippets/$(basename "$css")" "$force" ".obsidian/snippets/$(basename "$css")" "$check"
      done
    fi

    # 8. .obsidian/plugins/*/data.json — per-plugin defaults (recursive).
    #    Meta-Bind data.json is merged (buttonTemplates by id) to preserve
    #    operator settings; everything else is copy-if-absent / --force.
    if [[ -d "$templates_dir/.obsidian/plugins" ]]; then
      local src rel dst
      while IFS= read -r src; do
        rel="${src#"$templates_dir/.obsidian/"}"
        dst="$target/.obsidian/$rel"
        if [[ "$rel" == "plugins/obsidian-meta-bind-plugin/data.json" ]]; then
          _merge_meta_bind_data "$src" "$dst" "$check"
        else
          _seed_file "$src" "$dst" "$force" ".obsidian/$rel" "$check"
        fi
      done < <(find "$templates_dir/.obsidian/plugins" -type f -name '*.json')
    fi
  fi

  # 8b. M019 operator-self-reports — seed any study templates under
  #     templates/reports/studies/<id>/manifest.yaml into the vault's
  #     reports/studies/<id>/ subtree. Hardcoded "reports" path here:
  #     the wedge ships personal.reports_dir default = "reports" and
  #     operators who override the slug (e.g. to "analyses") will need
  #     to move the seeded manifest manually — an edge case acceptable
  #     for the wedge until S05 closeout documents the override path.
  if [[ -d "$templates_dir/reports/studies" ]]; then
    local manifest study_id rel_dir
    for manifest in "$templates_dir/reports/studies"/*/manifest.yaml; do
      [[ -f "$manifest" ]] || continue
      study_id="$(basename "$(dirname "$manifest")")"
      rel_dir="reports/studies/$study_id"
      _seed_file "$manifest" "$target/$rel_dir/manifest.yaml" "$force" "$rel_dir/manifest.yaml" "$check"
    done
  fi

  # 9. .claude/.env.example — secrets template (catalogue of recognised env vars).
  _seed_file "$templates_dir/.claude/.env.example" "$target/.claude/.env.example" "$force" ".claude/.env.example" "$check"

  # 10. Agent-task auto-wiring — discovered from prompts/agents/*.md `button:` frontmatter.
  #     Skipped in check mode (these are destructive merges + dashboard rewrites).
  if [[ "$check" != "1" ]]; then
    _merge_agent_shell_commands "$target" "$wiki_dir"
    _rewrite_dashboard_agent_buttons "$target" "$wiki_dir"
  fi
}
