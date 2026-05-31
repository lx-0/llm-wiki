#!/usr/bin/env bash
# lib/seed.sh — vault-template seeding logic shared by install.sh and `wiki seed`.
#
# Required helpers (loaded by both callers): ok, info, warn, err.
# Required tools: jq (for community-plugins.json merge).

# Guard against double-source.
[[ -n "${__WIKI_SEED_LOADED:-}" ]] && return 0
__WIKI_SEED_LOADED=1


# ── Internal: targeted-seed filter ─────────────────────────────────
# When `wiki seed <path>` targets one file, `_SEED_ONLY_DST` holds the
# absolute target path. Every file op asks this guard first: skip (return 0)
# unless its destination is the targeted one. Returns 1 (= don't skip) when
# not targeting, or when this IS the target — and marks `_SEED_ONLY_HIT` so
# the caller can warn if the requested path matched nothing seedable.
_seed_only_skip() {
  [[ -z "${_SEED_ONLY_DST:-}" ]] && return 1   # not targeting → never skip
  if [[ "$1" == "$_SEED_ONLY_DST" ]]; then
    _SEED_ONLY_HIT=1
    return 1
  fi
  return 0
}

# ── Internal: equivalence test (byte-equal, or JSON-equal ignoring key order) ──
# `cmp -s` flags a `.json` config as "drifted" whenever Obsidian rewrites it
# with reordered keys — a false positive that buries the real drifts in noise.
# For `.json` files, fall back to a canonical (`jq -S`) compare so only a
# genuine value/shape difference counts as drift. Returns 0 when equivalent.
_files_equivalent() {
  local a="$1" b="$2"
  cmp -s "$a" "$b" && return 0
  case "$a" in
    *.json)
      command -v jq >/dev/null 2>&1 || return 1
      local ca cb
      ca="$(jq -S . "$a" 2>/dev/null)" || return 1
      cb="$(jq -S . "$b" 2>/dev/null)" || return 1
      [[ "$ca" == "$cb" ]]
      ;;
    *) return 1 ;;
  esac
}

# ── Config overlays — engine-owned base ⊕ operator-owned delta ─────
# The drift problem: a seeded config file (graph.json, app.json, a plugin's
# data.json) must stay engine-updatable when new features add keys, BUT the
# operator also customises it. If the customisation lives in the file itself,
# every engine change is a force-vs-drift dilemma. The fix: the operator's
# delta lives in a SEPARATE untracked overlay at `<vault>/.wiki/custom/<rel>`
# and the live file is DERIVED as `template ⊕ overlay` (jq deep-merge, overlay
# wins). The operator edits the overlay, never the live file; `--force`
# re-derives, so it's non-destructive for overlay-managed files. Engine
# updates flow into the template half; customisations persist in the overlay.
_custom_root() { echo "$1/.wiki/custom"; }   # $1 = vault target

# Echo `base ⊕ overlay` (recursive merge, overlay wins). No overlay → base.
# Uses an ELEMENT-WISE deep merge, NOT jq's `*`: `*` merges objects but
# REPLACES arrays wholesale (right wins), so a sparse overlay array (only the
# operator's differing fields, e.g. a quickadd choice's tuned format) would
# obliterate the template's array — dropping every field that matched the
# template (names, ids, …). The recursive descent into arrays by index keeps
# template fields the overlay didn't touch. (Limitation: index-based, so an
# operator who REORDERS or mid-inserts array elements can misalign — documented
# as override-only; deletions aren't expressed either.)
_apply_overlay() {  # $1 = base file, $2 = overlay file
  if [[ -f "$2" ]] && command -v jq >/dev/null 2>&1; then
    jq -n --slurpfile a "$1" --slurpfile b "$2" '
      def deepmerge($x; $y):
        if   $y == null then $x
        elif ($x|type) == "object" and ($y|type) == "object" then
          reduce ($y | keys_unsorted[]) as $k ($x; .[$k] = deepmerge($x[$k]; $y[$k]))
        elif ($x|type) == "array" and ($y|type) == "array" then
          [ range(0; ([$x, $y] | map(length) | max)) as $i | deepmerge($x[$i]; $y[$i]) ]
        else $y end;
      deepmerge($a[0]; $b[0])
    ' 2>/dev/null && return 0
  fi
  cat "$1"
}

# Echo the minimal overlay: every leaf path where `cur` differs from `base`
# (new keys + changed values; leaf-level, so nested objects merge cleanly).
# Deletions aren't expressed — overlays are override-only by design.
_compute_overlay() {  # $1 = base file, $2 = cur file
  jq -n --slurpfile b "$1" --slurpfile c "$2" '
    ($b[0]) as $base | ($c[0]) as $cur
    | reduce ($cur | paths(scalars)) as $p ({};
        if ($base | getpath($p)) != ($cur | getpath($p))
        then setpath($p; $cur | getpath($p)) else . end)
  ' 2>/dev/null
}

_json_canon() { jq -S . "$1" 2>/dev/null; }              # canonical form of a file
_json_canon_str() { printf '%s' "$1" | jq -S . 2>/dev/null; }  # …of a string

# Seed a JSON config as `template ⊕ overlay`. Re-derive on --force or when
# missing; never clobber a drifted live file silently (operator may have
# edits not yet captured into an overlay — tell them how to make it durable).
_seed_json_overlay() {  # $1=src $2=dst $3=rel $4=force $5=check $6=target
  local src="$1" dst="$2" rel="$3" force="$4" check="${5:-0}" target="$6"
  [[ -f "$src" ]] || return 0
  _seed_only_skip "$dst" && return 0
  if ! command -v jq >/dev/null 2>&1; then
    _seed_file "$src" "$dst" "$force" "$rel" "$check"; return 0
  fi
  local overlay desired has_overlay=0
  overlay="$(_custom_root "$target")/$rel"
  [[ -f "$overlay" ]] && has_overlay=1
  desired="$(_apply_overlay "$src" "$overlay")"
  local ov_tag=""; [[ "$has_overlay" == 1 ]] && ov_tag=" (overlay applied)"

  if [[ "$check" == "1" ]]; then
    if [[ ! -f "$dst" ]]; then
      warn "missing $rel (run \`wiki seed\` to install)"
    elif [[ "$(_json_canon "$dst")" == "$(_json_canon_str "$desired")" ]]; then
      ok "up-to-date $rel$ov_tag"
    elif [[ "$has_overlay" == 1 ]]; then
      info "drifted $rel (live ≠ template⊕overlay — \`wiki seed $rel --force\` re-derives; or \`wiki seed --extract-custom $rel\` to capture new edits)"
    else
      info "drifted $rel (uncaptured edits — \`wiki seed --extract-custom $rel\` makes them survive engine updates)"
    fi
    return 0
  fi

  if [[ ! -f "$dst" ]]; then
    mkdir -p "$(dirname "$dst")"; printf '%s\n' "$desired" > "$dst"
    ok "seeded $rel$([[ "$has_overlay" == 1 ]] && echo ' (+overlay)')"
    return 0
  fi
  if [[ "$(_json_canon "$dst")" == "$(_json_canon_str "$desired")" ]]; then
    info "kept existing $rel (up-to-date$ov_tag)"
    return 0
  fi
  if [[ "$force" == "1" ]]; then
    mkdir -p "$(dirname "$dst")"; printf '%s\n' "$desired" > "$dst"
    ok "re-derived $rel from template$([[ "$has_overlay" == 1 ]] && echo '⊕overlay') (--force)"
    return 0
  fi
  if [[ "$has_overlay" == 1 ]]; then
    info "kept existing $rel (drifted from template⊕overlay; \`wiki seed $rel --force\` re-derives)"
  else
    info "kept existing $rel (drifted; \`wiki seed --extract-custom $rel\` captures your edits, then \`--force\` is safe)"
  fi
}

# Bootstrap an overlay from a file's CURRENT drift: delta(live, template) →
# `<vault>/.wiki/custom/<rel>`. After this, the live file == template⊕overlay,
# so seed/--force are non-destructive and engine updates flow in.
_extract_overlay() {  # $1=rel $2=target $3=templates_dir
  local rel="$1" target="$2" templates_dir="$3"
  local base="$templates_dir/$rel" dst="$target/$rel"
  local overlay; overlay="$(_custom_root "$target")/$rel"
  command -v jq >/dev/null 2>&1 || { err "jq required for --extract-custom"; return 1; }
  [[ -f "$base" ]] || { err "no engine template for '$rel' (not an overlay-managed file)"; return 1; }
  [[ -f "$dst" ]]  || { err "no live file at $dst"; return 1; }
  local delta; delta="$(_compute_overlay "$base" "$dst")"
  if [[ -z "$delta" || "$(_json_canon_str "$delta")" == "{}" ]]; then
    info "$rel already matches the engine template — no overlay needed"
    return 0
  fi
  mkdir -p "$(dirname "$overlay")"; printf '%s\n' "$delta" > "$overlay"
  local n; n="$(printf '%s' "$delta" | jq '[paths(scalars)] | length' 2>/dev/null)"
  ok "extracted overlay → .wiki/custom/$rel ($n override(s))"
  info "from now on edit .wiki/custom/$rel (not the live file); \`wiki seed $rel --force\` re-derives"
}

# Public: extract one file's overlay (used by `wiki seed --extract-custom <rel>`).
seed_extract_custom() {  # $1=target $2=wiki_dir $3=rel
  local templates_dir="$2/templates"
  _extract_overlay "$3" "$1" "$templates_dir"
}

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
  _seed_only_skip "$dst" && return 0

  if [[ "$check" == "1" ]]; then
    if [[ ! -f "$dst" ]]; then
      warn "missing $label (run \`wiki seed\` to install)"
    elif _files_equivalent "$src" "$dst"; then
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
  if _files_equivalent "$src" "$dst"; then
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
  _seed_only_skip "$dst" && return 0
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
  _seed_only_skip "$dst" && return 0
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


# ── Internal: merge .env.example (additive per-var stanza append) ──────
# `.env.example` is a catalogue of recognised env-vars (reference, not the
# live secrets). It drifts the moment an operator uncomments / annotates a
# line, so whole-file _seed_file would only ever say "kept existing (drifted)"
# — a NEW engine env-var (e.g. EXA_API_KEY) would never become discoverable
# without a destructive --force. This merge appends only the stanzas for
# active `KEY=` vars the operator's file is MISSING (matching either `KEY=`
# or a commented `# KEY=`), preserving everything they already have. Each
# appended stanza carries its contiguous doc-comment block from the template.
# Idempotent; check=1 reports what would be appended without writing; force=1
# overwrites wholesale (delegates to the caller's intent via cp).
_merge_env_example() {
  local src="$1" dst="$2" force="${3:-0}" check="${4:-0}"
  if [[ ! -f "$src" ]]; then
    return 0
  fi
  _seed_only_skip "$dst" && return 0
  if [[ ! -f "$dst" ]]; then
    if [[ "$check" == "1" ]]; then
      warn "missing .claude/.env.example (run \`wiki seed\` to install)"
      return 0
    fi
    mkdir -p "$(dirname "$dst")"
    cp "$src" "$dst"
    ok "seeded .claude/.env.example"
    return 0
  fi
  if [[ "$force" == "1" ]]; then
    mkdir -p "$(dirname "$dst")"
    cp "$src" "$dst"
    ok "overwrote .claude/.env.example (--force)"
    return 0
  fi

  # Active vars in the template = uncommented `KEY=` lines.
  local missing=() key
  while IFS= read -r key; do
    [[ -z "$key" ]] && continue
    # Present already if the operator has `KEY=` OR a commented `# KEY=`.
    if ! grep -qE "^[[:space:]]*#?[[:space:]]*${key}=" "$dst"; then
      missing+=("$key")
    fi
  done < <(grep -oE '^[A-Z_][A-Z0-9_]*=' "$src" | sed 's/=$//' | sort -u)

  if [[ ${#missing[@]} -eq 0 ]]; then
    info "kept existing .claude/.env.example (up-to-date — all engine vars present)"
    return 0
  fi

  if [[ "$check" == "1" ]]; then
    info "drifted .claude/.env.example (engine adds: ${missing[*]} — would append ${#missing[@]} stanza(s))"
    return 0
  fi

  # Append each missing var's stanza (its contiguous doc-comment block + the
  # `KEY=` line) from the template, preserving the operator's file verbatim.
  local appended=0
  for key in "${missing[@]}"; do
    local stanza
    stanza="$(awk -v key="$key" '
      /^[[:space:]]*$/ { buf=""; next }
      /^#/             { buf = buf $0 "\n"; next }
      $0 ~ "^" key "=" { printf "%s%s\n", buf, $0; found=1; exit }
      { buf="" }
      END { if (!found) exit 1 }
    ' "$src")"
    [[ -z "$stanza" ]] && stanza="$key="
    printf '\n\n%s\n' "$stanza" >> "$dst"
    appended=$((appended + 1))
  done
  ok ".claude/.env.example — appended ${appended} engine var(s): ${missing[*]}"
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
  _seed_only_skip "$dst" && return 0
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
  _seed_only_skip "$data" && return 0
  if ! command -v jq >/dev/null 2>&1; then
    warn "jq not available — skipping agent shell-commands merge"
    return 0
  fi
  local entries
  entries="$(uv run --quiet --project "$wiki_dir" python "$wiki_dir/scripts/dashboard/agent_buttons.py" shell-commands 2>/dev/null || echo '{}')"
  if [[ -z "$entries" ]] || [[ "$entries" == "{}" ]]; then
    return 0
  fi
  # The obsidian-shellcommands plugin stores `shell_commands` as an ARRAY of
  # `{id, ...}` objects; `agent_buttons.py` emits an OBJECT keyed by agent-id
  # with the `id` field omitted. Convert the generated map to array entries
  # (injecting `id` from the key), then replace-or-append into the operator's
  # array BY id — preserving every non-engine command the operator added.
  # (Pre-2026-05-31 this did `array + object`, which jq rejects → silent
  # "merge failed" + stale agent buttons.)
  local before after merged
  before="$(jq -r '.shell_commands | length' "$data" 2>/dev/null || echo 0)"
  merged="$(jq --argjson agents "$entries" '
    ($agents | to_entries | map(.value + {id: .key})) as $new
    | ($new | map(.id)) as $newids
    | .shell_commands = (
        [ (.shell_commands // [])[] | select(.id as $i | ($newids | index($i)) | not) ]
        + $new
      )
  ' "$data" 2>/dev/null || echo '')"
  if [[ -z "$merged" ]]; then
    warn "agent shell-commands merge failed"
    return 0
  fi
  printf '%s\n' "$merged" > "$data.tmp" && mv "$data.tmp" "$data"
  after="$(jq -r '.shell_commands | length' "$data")"
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
  _seed_only_skip "$dashboard" && return 0
  local result
  result="$(uv run --quiet --project "$wiki_dir" python "$wiki_dir/scripts/dashboard/agent_buttons.py" update-dashboard "$dashboard" 2>&1 || echo unchanged)"
  if [[ "$result" == "changed" ]]; then
    ok "dashboard.md — agent-buttons regions refreshed"
  else
    info "dashboard.md — agent-buttons already up to date"
  fi
}


# ── Public: seed all vault templates ───────────────────────────────
# Args: <target-vault-root> <wiki-dir> [force=0|1] [check=0|1] [only=<vault-rel-path>]
# check=1 reports drift without writing anything (read-only audit).
# only=<path> restricts the whole run to a single vault-relative file
#   (e.g. "AGENTS.md" or ".obsidian/app.json") — every other file op is
#   skipped via _seed_only_skip. Lets an operator surgically refresh one
#   stale file with --force without clobbering unrelated customizations.
seed_vault_templates() {
  local target="$1" wiki_dir="$2" force="${3:-0}" check="${4:-0}" only="${5:-}"
  local templates_dir="$wiki_dir/templates"

  # Targeted-seed setup: resolve the requested path to an absolute dst and
  # arm the per-file guard. _SEED_ONLY_HIT flips when a file op matches it.
  _SEED_ONLY_DST=""
  _SEED_ONLY_HIT=0
  if [[ -n "$only" ]]; then
    _SEED_ONLY_DST="$target/${only#/}"
  fi

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
        # graph.json / app.json / core-plugins.json — engine base ⊕ operator overlay.
        _seed_json_overlay "$f" "$target/.obsidian/$base" ".obsidian/$base" "$force" "$check" "$target"
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
          # extended-graph / quickadd / dataview / … — engine base ⊕ operator overlay.
          _seed_json_overlay "$src" "$dst" ".obsidian/$rel" "$force" "$check" "$target"
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
  #    Additive per-var merge (not whole-file _seed_file): appends only the
  #    stanzas for engine vars the operator's file is missing, so a new var
  #    (e.g. EXA_API_KEY) becomes discoverable without a destructive --force.
  _merge_env_example "$templates_dir/.claude/.env.example" "$target/.claude/.env.example" "$force" "$check"

  # 10. Agent-task auto-wiring — discovered from prompts/agents/*.md `button:` frontmatter.
  #     Skipped in check mode (these are destructive merges + dashboard rewrites).
  if [[ "$check" != "1" ]]; then
    _merge_agent_shell_commands "$target" "$wiki_dir"
    _rewrite_dashboard_agent_buttons "$target" "$wiki_dir"
  fi

  # Targeted run that matched nothing: tell the operator instead of silently
  # doing nothing (likely a typo or a non-seedable path).
  if [[ -n "$_SEED_ONLY_DST" && "$_SEED_ONLY_HIT" == "0" ]]; then
    warn "no seedable template matches '$only' — nothing done."
    warn "seedable paths: README.md, AGENTS.md, dashboard.md, knowledge.base,"
    warn "  .claude/.env.example, .obsidian/*.json, .obsidian/plugins/<p>/data.json,"
    warn "  Templates/*.md, knowledge/MOCs/*.md, reports/studies/<id>/manifest.yaml"
  fi
  _SEED_ONLY_DST=""
  _SEED_ONLY_HIT=0
}
