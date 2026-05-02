#!/usr/bin/env bash
# install.sh — bootstrap llm-wiki into a target directory.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/lx-0/llm-wiki/main/install.sh | bash
#   curl -fsSL .../install.sh | bash -s -- /path/to/vault
#   ./install.sh /path/to/vault           # local checkout
#
# Effects:
#   - Verifies prerequisites (git, jq, uv, bash 4+)
#   - Refuses to overwrite an existing .wiki/ (use `wiki update` instead)
#   - Clones the repo into <target>/.wiki/
#   - Seeds <target>/.wiki/config.yaml from config.example.yaml
#   - Runs `uv sync` inside .wiki/ so the venv lives at <target>/.wiki/.venv/
#   - Makes the wiki entry executable
#   - Prints next steps

set -euo pipefail

REPO_URL="${LLM_WIKI_REPO:-https://github.com/lx-0/llm-wiki.git}"
TARGET="${1:-$PWD}"
DEST="$TARGET/.wiki"

# ── Output helpers ───────────────────────────────────────────────────
if [[ -t 1 ]]; then
  G=$'\e[32m'; Y=$'\e[33m'; R=$'\e[31m'; B=$'\e[1m'; D=$'\e[2m'; N=$'\e[0m'
else
  G=""; Y=""; R=""; B=""; D=""; N=""
fi
ok()   { printf "%s✓ %s%s\n" "$G" "$*" "$N"; }
warn() { printf "%s! %s%s\n" "$Y" "$*" "$N" >&2; }
die()  { printf "%s✗ %s%s\n" "$R" "$*" "$N" >&2; exit 1; }

# ── Pre-flight ───────────────────────────────────────────────────────
[[ -d "$TARGET" ]] || die "Target directory does not exist: $TARGET"

if [[ -e "$DEST" ]]; then
  die "$DEST already exists. To update an existing install, run:
       cd $TARGET && ./.wiki/wiki update"
fi

missing=()
for cmd in git jq uv bash; do
  command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
done
if (( ${#missing[@]} > 0 )); then
  warn "Missing required tools: ${missing[*]}"
  cat >&2 <<EOF
Install hints:
  ${B}git${N}   pre-installed on most systems
  ${B}jq${N}    brew install jq          | apt install jq
  ${B}uv${N}    curl -LsSf https://astral.sh/uv/install.sh | sh
  ${B}bash${N}  brew install bash        (macOS ships an old 3.x — bash 4+ recommended)
EOF
  exit 1
fi

# Bash version check — features used: associative arrays, [[ ]], $'…'
bash_major=$(bash -c 'echo "${BASH_VERSINFO[0]}"')
if (( bash_major < 4 )); then
  warn "bash $bash_major detected. Some interactive features assume bash 4+."
fi

# ── Clone ────────────────────────────────────────────────────────────
printf "%scloning %s into %s …%s\n" "$D" "$REPO_URL" "$DEST" "$N"
git clone --depth 1 "$REPO_URL" "$DEST" >/dev/null 2>&1 \
  || die "git clone failed. Check URL: $REPO_URL"

# ── Seed config ──────────────────────────────────────────────────────
if [[ -f "$DEST/config.example.yaml" && ! -f "$DEST/config.yaml" ]]; then
  cp "$DEST/config.example.yaml" "$DEST/config.yaml"
  ok "config.yaml seeded from config.example.yaml"
fi

# ── Seed vault templates ─────────────────────────────────────────────
# Copy engine templates into the vault root if (and only if) the target
# files don't exist. Never overwrite. Designed for fresh vaults; on an
# existing vault, files the operator already authored win.
TEMPLATES_DIR="$DEST/templates"
if [[ -d "$TEMPLATES_DIR" ]]; then
  # AGENTS.md — article-schema spec consumed by every compile prompt.
  if [[ -f "$TEMPLATES_DIR/AGENTS.example.md" && ! -f "$TARGET/AGENTS.md" ]]; then
    cp "$TEMPLATES_DIR/AGENTS.example.md" "$TARGET/AGENTS.md"
    ok "AGENTS.md seeded from templates/AGENTS.example.md (edit Vault Owner + Language sections)"
  fi
  # dashboard.md — Obsidian Dataview home page (auto-opens via homepage plugin).
  if [[ -f "$TEMPLATES_DIR/dashboard.md" && ! -f "$TARGET/dashboard.md" ]]; then
    cp "$TEMPLATES_DIR/dashboard.md" "$TARGET/dashboard.md"
    ok "dashboard.md seeded"
  fi
  # _dashboard-stats.md — placeholder cache, overwritten after first wiki flush.
  if [[ -f "$TEMPLATES_DIR/_dashboard-stats.md" && ! -f "$TARGET/_dashboard-stats.md" ]]; then
    cp "$TEMPLATES_DIR/_dashboard-stats.md" "$TARGET/_dashboard-stats.md"
    ok "_dashboard-stats.md seeded (placeholder; refreshed by scripts/dashboard_stats.py)"
  fi
  # .obsidian/ plugin defaults — top-level *.json + per-plugin data.json files.
  if [[ -d "$TEMPLATES_DIR/.obsidian" ]]; then
    mkdir -p "$TARGET/.obsidian"
    for f in "$TEMPLATES_DIR/.obsidian"/*.json; do
      [[ -f "$f" ]] || continue
      base=$(basename "$f")
      if [[ ! -f "$TARGET/.obsidian/$base" ]]; then
        cp "$f" "$TARGET/.obsidian/$base"
        ok ".obsidian/$base seeded (approve community plugins on first Obsidian launch)"
      fi
    done
    # Per-plugin config (e.g. plugins/homepage/data.json) — preserves directory layout.
    if [[ -d "$TEMPLATES_DIR/.obsidian/plugins" ]]; then
      while IFS= read -r src; do
        rel="${src#"$TEMPLATES_DIR/.obsidian/"}"
        dst="$TARGET/.obsidian/$rel"
        if [[ ! -f "$dst" ]]; then
          mkdir -p "$(dirname "$dst")"
          cp "$src" "$dst"
          ok ".obsidian/$rel seeded"
        fi
      done < <(find "$TEMPLATES_DIR/.obsidian/plugins" -type f -name '*.json')
    fi
  fi
fi

# ── Wire skills into Claude Code ─────────────────────────────────────
# Each engine skill at .wiki/skills/<name>/ is symlinked to
# <vault>/.claude/skills/<name>/ so Claude Code discovers them
# automatically. After install, `wiki update` runs `wiki skills sync`
# as a post-step, so newly-pulled skills land in .claude/skills/ without
# a manual symlink dance (opt out via `wiki update --no-skills`).
SKILLS_SRC="$DEST/skills"
SKILLS_DST="$TARGET/.claude/skills"
if [[ -d "$SKILLS_SRC" ]]; then
  mkdir -p "$SKILLS_DST"
  symlinked=0
  for skill_path in "$SKILLS_SRC"/*/; do
    [[ -d "$skill_path" ]] || continue
    name=$(basename "$skill_path")
    target_link="$SKILLS_DST/$name"
    if [[ -L "$target_link" || -e "$target_link" ]]; then
      continue
    fi
    # Relative symlink so the link survives if the vault is moved
    # (as long as it stays alongside its own .wiki/).
    ln -s "../../.wiki/skills/$name" "$target_link"
    symlinked=$((symlinked + 1))
  done
  if (( symlinked > 0 )); then
    ok "linked $symlinked skill(s) into .claude/skills/"
  fi
fi

# ── Permissions ──────────────────────────────────────────────────────
chmod +x "$DEST/wiki"
[[ -x "$DEST/wiki" ]] || die "Failed to make $DEST/wiki executable"

# ── venv ─────────────────────────────────────────────────────────────
# Create the Python venv inside .wiki/ so it stays alongside the engine
# (not at the vault root). Subsequent uv invocations use --project .wiki.
printf "%ssyncing python deps into %s/.venv …%s\n" "$D" "$DEST" "$N"
if uv sync --project "$DEST" --quiet 2>/dev/null; then
  ok "venv ready at $DEST/.venv"
else
  warn "uv sync failed — run 'uv sync --project $DEST' manually before first use"
fi

# ── Done ─────────────────────────────────────────────────────────────
ok "llm-wiki installed at $DEST"
cat <<EOF

${B}Next steps:${N}
  cd $TARGET
  ./.wiki/wiki setup        ${D}# 5-question config wizard + agent hook install${N}
  ./.wiki/wiki status       ${D}# verify${N}
  ./.wiki/wiki help         ${D}# all commands${N}

${D}docs:    $DEST/README.md${N}
${D}config:  $DEST/config.yaml${N}
${D}venv:    $DEST/.venv      (run scripts via 'uv run --project $DEST python …')${N}
EOF
