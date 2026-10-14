---
name: De-slop arc — desktop app reads as vibe-coded; the codebase carries the same residue
description: Audit (2026-10-14) + three-milestone plan. M032 = desktop app (walls of text → visual feedback, design tells out, renderer rebuilt), M033 = engine modernisation + clean code, M034 = dispatcher/surface diet. Source pitch for M032-CONTEXT.md.
type: project
---

# De-slop arc

Operator request 2026-10-14 (paraphrased): the app looks like a typical vibe-coded app —
explanatory text everywhere, too little visual feedback ("more visuals, less wall of
text") — and the codebase should be modernised and clean-coded once. This file holds the
audit and the arc. **M032** (desktop) is planned from it (`M032-CONTEXT.md` /
`M032-ROADMAP.md`); M033 and M034 are pitched in §6 and get their own CONTEXT/ROADMAP
when their turn comes.

Scope reading: **"the app" = `desktop/`** — the only thing the repo calls an app
(`llm-wiki Desktop`, "App update available"). The TUI home screen (`wiki menu`) and the
CLI help were audited too and are compact and task-shaped; they are not in M032 (§7).

## 1. Evidence base

- **Headless render of the real built renderer** (`desktop/.vite/renderer/main_window/*.html`,
  built 2026-06-25, newer than every renderer source except `triage.ts` 2026-07-22) under a
  stub preload with fixture data — the DECISIONS 2026-06-24 harness, which was never
  committed, rebuilt as `/tmp/llmwiki-shots/render.py` (Playwright-Chromium via the engine
  venv). 17 PNGs: 7 surfaces × light/dark, panel in fresh / asked / expanded states.
  Regenerate: `cd /tmp/llmwiki-shots && <repo>/.venv/bin/python render.py`. M032-S01 ports
  the harness into the repo; until then it is scratch.
- **Baselines 2026-10-14, all green:** pytest 2011 passed / 1 skipped / 20.5 s · desktop
  vitest 53 passed / 1 skipped · eslint 0 errors / 9 warnings · `tsc --noEmit` **unusable**
  (866 errors inside `node_modules` — TypeScript 4.5.5 cannot parse vitest 4 typings;
  already noted in KNOWLEDGE "Desktop toolchain (C07)").
- Counts below are grep/ruff/AST censuses over `scripts/`, `hooks/`, `desktop/src/`.

## 2. Desktop findings — what the operator sees

Seven windows: panel (`index.html` + `renderer.ts` 877 LOC), Cockpit (`cockpit.ts` 923,
canvas), Atlas (`atlas.ts` 564, canvas), Browse, Triage, Settings, Onboarding. 4,769 LOC
TS (non-test) + 678 lines / 380 selectors CSS.

### 2.1 Wall of text

- **The panel is a stack of eleven sections.** At rest it asks the main process for
  **1,377 px** of height (1,665 px with Health/Sources/Advanced open); `PANEL_MAX_H` clamps
  at 640 px, so the daily surface *always* scrolls. Order: hint banner → stat line → the raw
  iCloud path (`~/Library/Mobile Documents/iCloud~md~obsidian/…`) → yield line → "3 things to
  tidy up" → update row → Add-to-wiki card → Recent → What's pending → Background capture
  (+ 2-line paragraph) → listener card → Sync sources (+ 2-line paragraph) → Advanced (5 rows,
  each with a hint sub-line) → Quit.
- **Prose embedded as UI:** nav-hint banner ("↑ The icons above open your Dashboard, Map,
  all your Notes, and the captures to sort." — exists because the five header icons are
  unlabeled), section hint under Background capture, provenance paragraph under Sync
  sources, five Advanced hint lines, three tooltips that are full sentences ("Turn newly
  captured material (notes, voice, screenshots, meetings) into wiki articles. ~1 min; uses
  AI.", "Safe — runs a quick cleanup in the background. Nothing is deleted.", "Do this now —
  runs in the background, usually under a minute"), "Added ✓ — it appears after the next
  Update.", three onboarding paragraphs, three settings sub-lines.
- **The same engine action is rendered up to three times with three verbs.** Screenshot,
  dream as the example: Health "12 pages need refreshing **[Fix]**" + What's pending "12 pages
  need refreshing **[Refresh]**" + Advanced "Refresh people & project pages **[Run]**". Cause:
  three independent lists (doctor checks, `menu --json` suggestions, the hardcoded
  `ADVANCED_COMMANDS`) rendered by three functions with no shared action model.
- **Vocabulary is patched at render time.** `friendlyHealth()` (6 regex rewrites of engine
  messages), `friendlyPending()` + `pendingVerb()` (10-entry maps keyed on the first argv
  word), `LISTENER_LABELS`. Any check or suggestion the maps don't know leaks engine jargon
  verbatim ("Ollama unreachable at 192.168.2.42:11434", fix text rendered as `code`). The
  principle (app speaks plain English) is right; the mechanism is the slop — the engine's
  `--json` contract should carry the operator-facing title and verb once, for every consumer.

### 2.2 Too little visual feedback

- **State is encoded as sentences.** Health = the line "3 things to tidy up"; capture = a
  word badge; activity = "+15 notes added today · +28 this week"; pending = text rows;
  compile = text + a 3 px bar. Nothing reads at a glance; nothing is comparable over time.
- **Actions give textual, transient feedback.** Running = spinner + "x of y"; done = the
  hint line swaps to "done ✓" / "failed" and the Add status clears after 6 s; a failed
  compile is `console.error` + "Update failed — try again" — no result stays visible, no
  detail is reachable, no transition marks the change.
- **Cockpit is the mirror failure: decoration without information.** Glowing icosphere,
  starfield, orbit rings, particles, ripples, `// PENDING` HUD labels, a monospace telemetry
  footer ("NOTES 2024 // UPDATED 2h // OLLAMA OFFLINE"). The orb's node labels are random
  entries; the one number on screen (2,024) is already in the panel. **Atlas** is Browse
  grouped by type (first seven entries per type, truncated titles) drawn as a curve tree
  with the same costume. Both are the "JARVIS / Minority-Report HUD" the CSS comment names.

### 2.3 Design tells (the `emil-unslop-design` list, measured)

- Violet/cyan **glow gradients** on every window (`radial-gradient` ×6 — "shared atmosphere",
  `body::before` on panel/browse/settings/onboarding), `backdrop-filter: blur` ×7, glow
  `box-shadow` ×14, `letter-spacing` ×25 (monospace uppercase HUD labels), 4 keyframe
  animations, ✦/✨ sparkle glyphs, **emoji as icons** (✉️ 📅 🎙️ 🎥 💬 ❤️ 🖥️ 🖼️ 🌐 🗂️ ▶️ 📥).
- **Palette is pasted Tailwind:** `GLOW` = violet-400 `#a78bfa`, `NODE` = sky-300 `#7dd3fc`,
  text `#e2e8f0` slate-200, `#93a4bd`, `#0b1220`. 54 distinct hex + 122 `rgba()` literals
  against 11 custom properties; the type palette lives twice (`lib/types.ts` `TYPE_COLOR` and
  hand-mirrored `.t-*` rules — the comment admits "if you change one here, change the
  matching rule too").
- Good and to keep: system font stack, native macOS vibrancy popover, the type badges and
  type-coloured edge on list rows, Browse and Triage layouts, the onboarding step cards.

### 2.4 Defects found en route (fix inside M032)

- **Light mode is broken on Triage and Settings.** Both use hardcoded dark hex on a
  `var(--win-bg)` body: in light mode the Triage title and every item summary are white on
  near-white (invisible), Settings' "lxw · 2,024 notes" is `#e2e8f0` on `#f3f3f5`.
  Screenshots `triage-light.png`, `settings-light.png`.
- Panel content height ignores `PANEL_MAX_H` by design, so the hint banner + answer push
  the status below the fold on every open.

### 2.5 Code slop (desktop)

- **Rendering model:** 62 `innerHTML` string templates, 82 `getElementById`, **64 module-level
  `let`** state variables, and a re-render cascade — every action calls `renderHealth()`,
  `renderAdvanced()`, `renderPending()`, `renderVault()`, `renderSources()` by hand. No state
  → view function; no component boundary; zero renderer tests (the 53 tests cover the main
  process only).
- **Duplicates:** `esc`/`escapeHtml` defined **6×** (renderer, browse, triage, settings,
  atlas, cockpit); `fmtAgo` 2× (atlas keeps its own next to `lib/time.ts`); `rgba()` 2×;
  copy/check/close SVG icon strings 2×; the brain logo SVG pasted into 4 HTML files;
  `TYPE_COLOR` in TS + CSS.
- **Template residue:** `renderer.ts` opens with the 27-line Electron-Forge boilerplate
  comment; `package.json` says `"name": "desktop"`, `"productName": "desktop"`,
  `"description": "My Electron application description"`, `"keywords": []`.
- **Toolchain rot:** TypeScript **4.5.5** (Dec 2021) with no `strict`; ESLint 8 + legacy
  `.eslintrc.json` + typescript-eslint 5; no formatter; no typecheck gate (see §1). Current
  and fine: Electron 42, Vite 5, Vitest 4, Electron-Forge 7.

## 3. Engine findings — the same disease in Python and bash

190 files / 51,155 LOC under `scripts/` + `hooks/`; 2011 tests in 20 s. The 0.3.0
architecture-deepening arc built the right seams (frontmatter grammar, state store, SDK
harness, collector harness, errors.swallow); this audit finds the *residue around* them.

### 3.1 Tooling gaps (modernisation)

- **No formatter has ever run:** `ruff format --check` → **145 of 190** files would change.
- **No lint policy:** `[tool.ruff]` carries only `line-length`; ruff is absent from
  pre-commit (gitleaks + hygiene hooks only) and from CI (gitleaks only). With a modern rule
  set (`E,F,I,UP,B,SIM,N,RUF,PL,C90`) ruff reports ~1,750 findings: E501 390 · **RUF100
  unused-noqa 183 (of 231 `noqa` total)** · PLC0415 import-outside-top-level 173 · PLR2004
  magic values 151 · I001 unsorted imports 109 · C901 complex 98 · PLR0912 53 · UP017 50 ·
  F401 unused imports 39 · PLR0915 38 · PLR0913 32 · PLR0911 30 · F541 22 · PLW1510
  subprocess-without-check 19 · E402 17. (`deepening-arc-followups.md` already names the
  `[tool.ruff.lint]` policy as an open item.)
- **No type checker** (mypy/pyright/ty absent); 56 `Any`; `from __future__ import annotations`
  in 148 files on a Python ≥ 3.12 floor.
- **CI never runs the test suite.** `.github/workflows/secrets-scan.yml` is the only workflow.

### 3.2 Structure and duplication

- **`scripts/` is not a package:** no `__init__.py`, **36 top-level entry scripts** (five
  hyphenated and therefore un-importable: `ingest-html.py`, `optimize-claude-md.py`,
  `process-inbox.py`, `retry-failed-flushes.py`, `review-wiki.py`), **68 `sys.path.insert`**
  hacks, tests via `pythonpath = ["scripts"]` — which is why `core.*` and `scripts.core.*`
  are distinct module instances under pytest (KNOWLEDGE C01). `cli.py` re-spawns every
  Python handler as a child process; with the bash layer that is three processes per
  command.
- **God modules:** `dream.py` 2,014 · `core/health.py` 1,611 · `lint.py` 1,284 ·
  `collectors/gmeet.py` 1,148 · `migrations/migrate_config_keys.py` 1,102 ·
  `core/sdk_helpers.py` 1,053 · `cli.py` 1,040. (`core/config_schema.py` 1,185 is 72 %
  comment by design — it generates `docs/config.md`; leave it.)
- **15 functions ≥ 150 lines (AST-measured):** `dream_entity` 347 · `run_sdk_query` 320 ·
  `compile.main` 317 · `gmeet._run_one_account` 295 · `maybe_generate_curiosity_requests` 292
  · `render_summary` 239 · `query.main` 236 · `study.cmd_run` 222 · `compile_source` 212 ·
  `maybe_generate_folder_requests` 202 · `_persist_report` 192 ·
  `calendar_collector._run_one_account` 188 · `run_inference` 164 · `maybe_extract_takes` 161
  · `_run_compile_route` 154.
- **Seams exist, callers never migrated:** **17 private frontmatter entry points**
  (`_read_frontmatter` ×5, `_parse_frontmatter` ×5, `_split_frontmatter`/`split_frontmatter`
  ×6, `_read_frontmatter_field`) next to `core/frontmatter.py`, "the single grammar";
  **5 slugify** implementations (`core/utils.slugify`, `scan_youtube.slugify`, and a
  byte-identical `_slugify(text, max_len=60)` in jamie/calendar/gmeet); `_setup_logging` ×4;
  `_load_state`/`_save_state` ×3 each next to `core/state_store.py`; `_append_daily_rollup`
  ×3; `_scan_inbox` ×3. Consumer-grep each site before touching it — some may already
  delegate (CLAUDE.md "unused only after a repo-wide grep").
- 529 `print(` against 746 log calls — CLI output and logging are mixed despite
  `core/console.py` being the shared formatter.

### 3.3 Bash layer

`wiki` 821 lines + `lib/*.sh` 1,715 + `install.sh` 206 = **2,742 lines of bash**, owning
setup / config / hooks / skills / seed / update / menu / doctor / status / install-shortcut
/ version plus dream argv routing, in front of the 1,040-line Python dispatcher. The banner
printed by bash lands before any `--json` payload, so consumers "parse from the first `{`"
(KNOWLEDGE C06). Two dispatch layers, two help systems, three process hops.

## 4. Principles for the arc

1. **Show state, don't narrate it.** Every status that matters gets a shape (ring, meter,
   sparkline, pill) and a number; prose explains nothing the shape already says. Tooltip ≤
   6 words. Zero paragraphs inside the panel.
2. **One action, one place, one verb.** A single `Action` model merges doctor checks, menu
   suggestions and the advanced list; each action renders once, with the verb the engine
   declares.
3. **The engine owns its vocabulary.** `menu --json` / `doctor --json` carry `title`, `verb`,
   `group`, `argv` for operators; the app renders them verbatim — no regex patching, no
   per-command maps (keeps the DECISIONS 2026-06-24 principle, replaces its mechanism).
4. **Feedback persists until dismissed.** Running = progress on the row; done/failed = a
   result pill that stays, with the detail one click away.
5. **Tokens, not literals.** Colour, space, radius and type scale live in CSS custom
   properties with one source; light/dark are two token sets; the type palette is generated
   from one definition.
6. **Costume off.** No glow gradients, no HUD monospace labels, no starfields, no emoji
   icons, no sparkles. Native macOS material is the atmosphere.
7. **No soft deprecation, no parallel rebuild.** Surfaces that encode nothing are deleted in
   one commit; frameworks and tools are adopted (OSS-first), not re-implemented.
8. **Every slice leaves the app usable** and ends with the screenshot gate (render harness →
   zoom-crop review) plus a DMG rebuild for the operator.

## 5. Target design (M032)

**Panel — 360 × ≤ 640 px, no scroll at rest.**

1. Header: brand · vault pill · **labeled** segmented nav (Overview · Notes · Inbox ⟨n⟩ ·
   Settings). Labels retire the hint banner.
2. Ask bar (hero, unchanged role); the answer card replaces the status strip while open.
3. **Status strip — three glyph tiles:** Library (count + 14-day adds sparkline) · Health
   (ring: ok / amber / red + count) · Capture (level meter + state word). Click expands the
   tile inline.
4. **Next up — the one action list** (≤ 5 rows): title · verb button; running = inline
   progress bar on the row; done/failed = result pill that persists until the panel closes.
5. Recent (5 rows — keep as is, it works).
6. Footer: `+ Add link` (collapsed), Sources (sheet), Quit.

Removed from the panel: raw vault path, yield text line (now the sparkline), both section
paragraphs, the five Advanced hint lines (actions move into Next up), the nav-hint banner,
emoji icons (→ one monochrome SVG set).

**Overview window replaces Cockpit + Atlas** — four real charts, dataviz-skill rules:
notes added per day (30-day bars), type distribution (horizontal bars), health (ring +
list), capture timeline (24 h mic/system freshness strip), plus the pending queue. The
icosphere, stars, orbits, particles, HUD labels and the Atlas tree are deleted; Browse +
type filter already covers Atlas's one function. A true link graph is a backlog item if ever
wanted.

**Browse / Triage / Settings / Onboarding** stay structurally; they move to tokens (fixes
light mode), lose the glow layers, and get the copy diet (onboarding: one sentence per
step; settings: label + value, no sub-sentences).

## 6. The arc

| Milestone | Scope | Size | Exit signal |
| --- | --- | --- | --- |
| **M032 — Desktop de-slop** (now) | §5 design, engine JSON contract, renderer rebuilt, toolchain, harness | L, 5 slices | panel ≤ 640 px at rest with zero paragraphs; every action once; three visual status shapes; light mode correct everywhere; `tsc --strict` + Biome green; harness committed; blind learnability ≥ 8/10 (M029: 6/10) |
| **M033 — Engine modernisation + clean code** | format + lint policy + pre-commit + CI (pytest, ruff, desktop tests); `scripts/` as a package (no `sys.path` hacks, no hyphenated scripts, `python -m` dispatch keeping process isolation); dedupe onto the existing seams (17 → 1 frontmatter, 5 → 1 slugify, state/logging/rollup); split the 15 long functions and the four god modules where it pays; pyright/ty `basic` on `core/` then outward; typed `--json` contracts shared with the desktop | L, 5 slices | `ruff check` + `ruff format --check` + `pyright` green in pre-commit and CI; 0 unused `noqa`; 0 private frontmatter parsers; no function ≥ 150 lines in `scripts/` outside generated tables |
| **M034 — Dispatcher + surface diet** | `wiki` becomes a thin bootstrap (vault guard, venv, `exec python -m wiki …`); setup/config/hooks/skills/seed/update/menu/doctor/status move to Python; `lib/*.sh` retire; one help system; README ≤ 300 lines (standing rule), AGENTS.md/docs trimmed to what consumers read; TUI cosmetics (sparkle, commit hash in the header) | M | one process hop per command; bash ≤ 150 lines; `wiki help` and `wiki menu` derive from one table |

Order: M032 first because it is the complaint; it also lands the engine JSON contract that
M033's typed contracts build on. M033 before M034 because the package layout decides how
the bash commands are ported. The three STATE candidates from 2026-08-28 (curiosity dedup,
flush orphan recovery, MOC auto-maintenance) stay queued; curiosity dedup (S, saves real
money) can run as an ad-hoc in parallel if the operator wants.

**M033 format commit:** one mechanical `ruff format` commit, hash recorded in
`.git-blame-ignore-revs`, no logic changes in the same commit.

## 7. Decisions this arc reopens (DECISIONS 2026-06-24)

- "One authored product — shared atmosphere (violet core-glow → clean charcoal)": **reopened**;
  the glow *is* the tell. Cohesion comes from tokens and the type palette instead.
- "The dense panel is NOT gutted": **reopened** by the operator's request. The panel stays
  the daily power surface, but as a status strip + one action list, not eleven sections.
- "The cockpit's `//` HUD labels are deliberately cockpit-only": **moot** — Cockpit and
  Atlas are replaced by the Overview window.
- "App speaks plain English, engine keeps operator terms": **kept**; mechanism moves into
  the engine's `--json` contract (§4.3).
- "Render-verification harness in /tmp": **superseded** — the harness is committed in S01.

## 8. Explicitly not in this arc

- `wiki menu` (TUI) and `wiki help`: compact, task-shaped, grouped; only the ✨ glyph and
  the commit hash in the header are cosmetic (M034).
- `docs/*.excalidraw`: untouched unless the engine architecture changes (the JSON contract
  does not).
- Signing/notarisation, auto-update (operator-gated, unchanged from M029).
- The ytstack process artifacts (`DECISIONS.md` 306 KB, `KNOWLEDGE.md` 325 KB): operator
  process, not product.

## 9. Open decisions (answers go to `M032-CONTEXT.md` → Decisions)

1. **Renderer framework.** Recommendation: **Svelte 5** (in the operator's stack, Vite-native,
   Electron-Forge's vite plugin needs no change) — it removes the innerHTML/state-cascade
   class structurally and makes renderer tests possible. Alternative without a framework:
   `lit-html` templates + one store module. Hand-rolled view-model = rebuilding a framework
   (OSS-first says no). Must be decided before S03.
2. **Cockpit + Atlas fate.** Recommendation: delete both, build the Overview window (§5).
   Alternative: keep Atlas as a backlog "real link graph" pitch.
3. **Lint/format tool for the desktop.** Recommendation: **Biome** (stack default) replaces
   ESLint + typescript-eslint; `tsc --noEmit --strict` becomes the typecheck gate after the
   TS 5 upgrade.

## 10. Risks

- **Taste cannot be delegated.** Synthetic personas catch comprehension gaps, not whether
  the operator likes it. Every M032 slice ends with the screenshot gate *and* an operator
  look at the DMG before the next slice starts.
- **The panel is the operator's daily surface.** Rebuild it behind the harness: old
  renderer stays until the new one passes the same fixture states; swap in one commit.
- **Engine JSON contract touches other consumers** (TUI, `menu_context`, tests, the
  `home-screen-ux.md` probe-registry item). Consumer-grep rule applies; bump a `schema`
  field in both payloads.
- **Svelte migration is a rewrite** of ~2.5 k renderer LOC. Mitigation: per window, panel
  first, fixtures shared with the harness, no feature additions during the port.
