#!/usr/bin/env bash
# lib/seed.sh — vault-template seeding logic shared by install.sh and `wiki seed`.
#
# Required helpers (loaded by both callers): ok, info, warn, err.
# Required tools: jq (for community-plugins.json merge).

# Guard against double-source.
[[ -n "${__WIKI_SEED_LOADED:-}" ]] && return 0
__WIKI_SEED_LOADED=1


# ── Internal: copy if absent / overwrite if --force ────────────────
_seed_file() {
  local src="$1" dst="$2" force="$3" label="${4:-}"
  [[ -z "$label" ]] && label="$(basename "$dst")"
  if [[ ! -f "$src" ]]; then
    return 0  # template missing — silently skip
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
  info "kept existing $label (engine version available; rerun with --force to overwrite)"
}


# ── Internal: merge community-plugins.json (additive union) ────────
# This is always safe — we only ADD missing engine plugins to the list,
# never remove operator-added entries. Idempotent.
_merge_community_plugins() {
  local src="$1" dst="$2"
  if [[ ! -f "$src" ]]; then
    return 0
  fi
  if [[ ! -f "$dst" ]]; then
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
  printf '%s\n' "$merged" > "$dst.tmp" && mv "$dst.tmp" "$dst"
  after="$(jq -r 'length' "$dst")"
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
  local src="$1" dst="$2"
  if [[ ! -f "$src" ]]; then
    return 0
  fi
  if [[ ! -f "$dst" ]]; then
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
  printf '%s\n' "$merged" > "$dst.tmp" && mv "$dst.tmp" "$dst"
  after="$(jq -r '(.enabledCssSnippets // []) | join(",")' "$dst")"
  if [[ "$before" != "$after" ]]; then
    ok "appearance.json — enabledCssSnippets [$before] → [$after]"
  else
    info "appearance.json — enabledCssSnippets already up to date"
  fi
}


# ── Public: seed all vault templates ───────────────────────────────
# Args: <target-vault-root> <wiki-dir> [force=0|1]
seed_vault_templates() {
  local target="$1" wiki_dir="$2" force="${3:-0}"
  local templates_dir="$wiki_dir/templates"

  if [[ ! -d "$templates_dir" ]]; then
    warn "no templates dir at $templates_dir"
    return 1
  fi

  # 1. AGENTS.md — vault-owner editable schema.
  _seed_file "$templates_dir/AGENTS.example.md" "$target/AGENTS.md" "$force" "AGENTS.md"

  # 2. dashboard.md — Obsidian Homepage target.
  _seed_file "$templates_dir/dashboard.md" "$target/dashboard.md" "$force" "dashboard.md"

  # 3. _dashboard-stats.md — placeholder cache; refreshed post-flush.
  _seed_file \
    "$templates_dir/_dashboard-stats.md" \
    "$target/_dashboard-stats.md" \
    "$force" \
    "_dashboard-stats.md"

  # 4. Templates/*.md — typed-note templates consumed by QuickAdd.
  if [[ -d "$templates_dir/Templates" ]]; then
    local tpl
    for tpl in "$templates_dir/Templates"/*.md; do
      [[ -f "$tpl" ]] || continue
      _seed_file "$tpl" "$target/Templates/$(basename "$tpl")" "$force" "Templates/$(basename "$tpl")"
    done
  fi

  # 5. .obsidian/*.json — top-level configs.
  if [[ -d "$templates_dir/.obsidian" ]]; then
    mkdir -p "$target/.obsidian"
    local f base
    for f in "$templates_dir/.obsidian"/*.json; do
      [[ -f "$f" ]] || continue
      base="$(basename "$f")"
      if [[ "$base" == "community-plugins.json" ]]; then
        _merge_community_plugins "$f" "$target/.obsidian/$base"
      elif [[ "$base" == "appearance.json" ]]; then
        _merge_appearance_json "$f" "$target/.obsidian/$base"
      else
        _seed_file "$f" "$target/.obsidian/$base" "$force" ".obsidian/$base"
      fi
    done

    # 6. .obsidian/snippets/*.css — CSS snippets for the dashboard layout.
    if [[ -d "$templates_dir/.obsidian/snippets" ]]; then
      mkdir -p "$target/.obsidian/snippets"
      local css
      for css in "$templates_dir/.obsidian/snippets"/*.css; do
        [[ -f "$css" ]] || continue
        _seed_file "$css" "$target/.obsidian/snippets/$(basename "$css")" "$force" ".obsidian/snippets/$(basename "$css")"
      done
    fi

    # 7. .obsidian/plugins/*/data.json — per-plugin defaults (recursive).
    if [[ -d "$templates_dir/.obsidian/plugins" ]]; then
      local src rel dst
      while IFS= read -r src; do
        rel="${src#"$templates_dir/.obsidian/"}"
        dst="$target/.obsidian/$rel"
        _seed_file "$src" "$dst" "$force" ".obsidian/$rel"
      done < <(find "$templates_dir/.obsidian/plugins" -type f -name '*.json')
    fi
  fi
}
