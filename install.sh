#!/usr/bin/env bash
# install.sh — bootstrap llm-wiki into a target directory.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/lx-0/llm-wiki/main/install.sh | bash
#   curl -fsSL .../install.sh | bash -s -- /path/to/vault
#   ./install.sh /path/to/vault           # local checkout
#
# Effects:
#   - Verifies prerequisites (git, uv, bash 4+)
#   - Refuses to overwrite an existing .wiki/ (use `wiki update` instead)
#   - Clones the repo into <target>/.wiki/
#   - Seeds <target>/.wiki/config.yaml from config.example.yaml
#   - Makes the wiki entry executable
#   - Runs `wiki seed`, whose bootstrap creates the engine's Python environment
#     (<target>/.wiki/.venv, or ~/.venvs/<vault>-wiki for a cloud-synced vault)
#   - Links the engine skills (`wiki skills sync`)
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
for cmd in git uv bash; do
  command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
done
if (( ${#missing[@]} > 0 )); then
  warn "Missing required tools: ${missing[*]}"
  cat >&2 <<EOF
Install hints:
  ${B}git${N}   pre-installed on most systems
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

# ── Strip engine-dev artifacts ───────────────────────────────────────
# Keep the engine's own dev-tracking out of the operator's vault tree.
# These paths stay git-tracked (so `wiki update`'s `git pull --ff-only`
# never hits a dirty working tree — a plain `rm -rf` would, since git
# would try to restore the deleted tracked files on the next pull and
# abort). git's sparse-checkout omits them from the *checkout* instead,
# and the setting persists in .git/, so every future `wiki update`
# honours it automatically — no update-side step required.
STRIP_LIST=( ".ytstack" "tests" )   # engine dev-tracking + pytest suite
sparse_patterns=( '/*' )
for p in "${STRIP_LIST[@]}"; do sparse_patterns+=( "!/$p/" ); done
if git -C "$DEST" sparse-checkout set --no-cone "${sparse_patterns[@]}" 2>/dev/null; then
  ok "stripped engine-dev artifacts from vault (${STRIP_LIST[*]})"
else
  warn "sparse-checkout unavailable — ${STRIP_LIST[*]} remain in $DEST (cosmetic only)"
fi

# ── Seed config ──────────────────────────────────────────────────────
if [[ -f "$DEST/config.example.yaml" && ! -f "$DEST/config.yaml" ]]; then
  cp "$DEST/config.example.yaml" "$DEST/config.yaml"
  ok "config.yaml seeded from config.example.yaml"
fi

# ── Seed vault templates: the choice ─────────────────────────────────
# The seeding itself is `wiki seed`, run once the engine's environment is
# synced (below). When stdin is a TTY (or /dev/tty can be opened, which covers
# curl|bash in a real terminal), ask once for keep / overwrite / abort. When
# headless, keep — matching the original contract.
info() { printf "ℹ %s\n" "$*"; }

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
  # Reuse /dev/tty so curl|bash still gets an interactive prompt. Open it to
  # find out: `-r /dev/tty` only tests the permission, which holds without a
  # controlling terminal too — the `read` then failed ("Device not
  # configured") and `set -e` aborted a headless install over an existing vault.
  if [[ -t 0 ]] || { : </dev/tty; } 2>/dev/null; then
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

# ── Permissions ──────────────────────────────────────────────────────
chmod +x "$DEST/wiki"
[[ -x "$DEST/wiki" ]] || die "Failed to make $DEST/wiki executable"

# ── Seed vault templates (and the engine's environment) ──────────────
# `wiki seed` is the first `wiki` call. Its bootstrap creates the engine's Python
# environment where the engine's own rule puts it — .wiki/.venv, or ~/.venvs/<vault>-wiki
# for a vault in iCloud Drive / CloudStorage, where eviction SIGKILLs a running binary —
# and stamps it, so the next command does not sync again. This installer used to restate
# that rule through lib/common.sh (folded into `wiki` in M034-S05-T05) and ran its own
# `uv sync`, which left no stamp. Seed's vault guard wants .obsidian/: the old bash seed
# created it silently, so a fresh directory becomes a vault here, as before.
mkdir -p "$TARGET/.obsidian"
seed_args=(seed)
[[ "$seed_force" == 1 ]] && seed_args+=(--force)
if ! (cd "$TARGET" && "$DEST/wiki" "${seed_args[@]}"); then
  warn "seeding failed — once the environment is ready, run: cd '$TARGET' && ./.wiki/wiki seed"
fi

# ── Wire skills into Claude Code ─────────────────────────────────────
# Each engine skill at .wiki/skills/<name>/ is linked into <vault>/.claude/skills/ so
# Claude Code discovers it: `wiki skills sync`, which `wiki update` also runs after every
# pull (opt out there with `--no-skills`).
if ! (cd "$TARGET" && "$DEST/wiki" skills sync); then
  warn "linking the engine skills failed — run: cd '$TARGET' && ./.wiki/wiki skills sync"
fi

# ── Done ─────────────────────────────────────────────────────────────
ok "llm-wiki installed at $DEST"
cat <<EOF

${B}Next steps:${N}
  cd $TARGET
  ./.wiki/wiki setup        ${D}# 6-question config wizard + agent hook install${N}
  ./.wiki/wiki status       ${D}# verify${N}
  ./.wiki/wiki help         ${D}# all commands${N}

${D}docs:    $DEST/README.md${N}
${D}config:  $DEST/config.yaml${N}
${D}python:  run engine commands via './.wiki/wiki …' — it knows where the environment is${N}
EOF
