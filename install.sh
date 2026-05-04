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
# Delegates to lib/seed.sh — same code is reused by `wiki seed` for
# in-place re-seeding on existing installs. When stdin is a TTY (or
# /dev/tty is reachable, which covers curl|bash when run in a real
# terminal), prompt once for keep / overwrite / abort. When non-TTY
# (true headless), default to keep — matching the original contract.
info() { printf "ℹ %s\n" "$*"; }
# shellcheck source=lib/seed.sh
source "$DEST/lib/seed.sh"

seed_force=0
# Detect whether the operator already has any seedable files. If not, the
# prompt is pointless — there's nothing to overwrite or skip.
has_existing=0
for probe in \
    "$TARGET/AGENTS.md" \
    "$TARGET/dashboard.md" \
    "$TARGET/knowledge.base" \
    "$TARGET/.obsidian/community-plugins.json"; do
  [[ -e "$probe" ]] && { has_existing=1; break; }
done

if (( has_existing )); then
  # Reuse /dev/tty so curl|bash still gets an interactive prompt.
  if [[ -t 0 ]] || [[ -r /dev/tty ]]; then
    printf "\n%sExisting vault files detected at %s%s\n" "$Y" "$TARGET" "$N"
    printf "  ${B}k${N})eep existing — engine versions will NOT overwrite your edits ${D}(default)${N}\n"
    printf "  ${B}o${N})verwrite — replace template files with engine defaults ${D}(your edits in those files are lost)${N}\n"
    printf "  ${B}a${N})bort — stop install; .wiki/ is already cloned, run installer again later\n"
    printf "Choose [k/o/a]: "
    if [[ -t 0 ]]; then
      read -r seed_choice
    else
      read -r seed_choice </dev/tty
    fi
    case "${seed_choice:-k}" in
      o|O|overwrite) seed_force=1; ok "will overwrite existing template files" ;;
      a|A|abort)     warn "aborted before seeding. .wiki/ remains at $DEST."; exit 0 ;;
      *)             info "keeping existing files (engine defaults skipped where files already exist)" ;;
    esac
  else
    info "non-interactive install — keeping existing files (rerun './.wiki/wiki seed --force' to overwrite)"
  fi
fi

seed_vault_templates "$TARGET" "$DEST" "$seed_force"

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
