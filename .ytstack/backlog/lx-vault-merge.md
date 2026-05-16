# Merge `lx/` vault into `lxw/`

Dissolve the legacy `lx/` Obsidian vault (114 MDs, last active ~2026-05-02, separate git repo with `no-push.invalid` remote — local-only history) and import its valuable content into the active `lxw/` engine-vault. End state: one vault, one git, `lx/` archived to tarball and removed from iCloud.

## Why now

- Operator confirmed: "lx sollte danach obsolete werden" (2026-05-16). Already not maintained.
- Two parallel iCloud vaults under `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/` create real cognitive overhead (which vault to open? which has the strategy doc?) and Spotlight/Obsidian-Search duplication.
- The audit of `lx/` surfaced three structural concepts worth lifting independently (`archives-flag.md`, `areas-bucket.md`, `domain-frontmatter.md`) — those have value regardless of merge timing, and one of them (`areas-bucket`) is a soft prerequisite.
- Without merge, `lx/` content becomes a knowledge dead zone: indexed in nothing, linked from nothing, accessible only by remembering which vault to open.

## Content map (audit findings)

| lx-Folder | MDs | Character | Target in lxw |
|---|---|---|---|
| `🌈 Company/` | 37 | Yesterday strategy, handovers, service-architecture per person/topic | Mostly entity-pages (people, projects, concepts) — needs entity-pages-State+Timeline schema |
| `👤 Personal/` | 17 | personal Areas + Projects, PARA-structured | Mostly `knowledge/areas/` (needs `areas-bucket.md` shipped first) + some `knowledge/projects/` |
| `🤖 AI/` | 11 | AI tools, skills (e.g. sunoflow-skill) | `knowledge/concepts/` |
| `📥 Inbox/` | 14 | unprocessed scratch | `lxw/inbox/` (engine-managed) OR drop if stale |
| Top-level loose | 12 | strategy papers, handovers, dashboards | Entity-pages (yesterday-strategy → knowledge/projects/yesterday-*) |
| `Archives/` | 5 | already-cold lx-side archives | `knowledge/**/*.md` with `archived: true` (needs `archives-flag.md` shipped first) |
| `Templates/` | 7 | PARA-shape templates | **Drop.** lxw uses different templates. |
| Excalidraw + PDF + docx | — | `Yesterday.excalidraw` (4MB), `Yesterday(1).excalidraw` (11MB), `PixelTales.pdf`, etc. | `lxw/Excalidraw/imported-lx/` + `lxw/raw/papers/imported-lx/` for PDF |

~85% of content is entity-shaped (per-person handovers, per-service architecture, per-topic strategy). This is exactly the gbrain entity-pages pattern that `entity-pages-state-timeline.md` proposes.

## The two non-trivial questions

**Q1: Where does merged content live, given lxw's substrate-vs-knowledge split?**

Considered three strategies:
- **A) Substrate-merge** (lx → `raw/notes/lx/` → engine re-compiles) — rejected: would re-distill already-distilled strategy docs through a distill-compiler, lossy and costly; also produces duplicate concept pages where lxw already has them (emmett, openclaw, infisical).
- **B) Direct-import** (lx → `knowledge/` with `compiled_from: hand` frontmatter, engine skips) — viable but requires engine "skip hand-curated" mechanism that doesn't exist yet.
- **C) Entity-pages-anchored migration** (lx becomes the demand-trigger for shipping `entity-pages-state-timeline.md` as a milestone; per-entity pages are populated from lx content as initial Timeline entry + State block) — **recommended.** Solves "lxw needs entity-pages" + "lx needs a home" simultaneously. Larger scope but ships real architecture, not just file moves.

Chosen approach: **Phased hybrid (C+B)**:
1. Cold-storage everything immediately (Phase 0)
2. Bulk-import non-entity content into engine-excluded `lxw/imported/lx/` for Single-Vault-search reach (Phase 1, fast)
3. Ship `archives-flag.md` + `areas-bucket.md` (prerequisites)
4. Ship `entity-pages-state-timeline.md` as a milestone (does the heavy lifting)
5. Migrate `imported/lx/` content into proper `knowledge/{people,projects,concepts,areas}/` shape per the entity-pages schema (Phase 2)
6. Cleanup `imported/lx/` and dissolve `lx/` vault (Phase 3)

**Q2: Git history — preserve or discard?**

- `lx/` git remote is `no-push.invalid` (verified 2026-05-16). Pure local-only history, no shared/published value.
- Tarball with `.git/` intact preserves the history for any "what did I write about X 6 months ago" forensic need
- **Decision: do not subtree-merge.** lxw IS a git repo (verified — lives inside iCloud folder, surprising but real). Importing as plain copy + single commit in lxw is cleaner than git-subtree gymnastics for local-only history.

## Phases (concrete plan)

### Phase 0 — Cold-storage (1 hour, blocking)

Cross-vault write — needs explicit operator authorization per REGEL #2 before each step.

1. Inspect `lx/` dirty state (already known: uncommitted `.claude/skills/excalidraw-diagram/*` — these are stale duplicates of the now-shared `lx-0/skills` plugin; verify before discarding)
2. Decide per dirty file: commit-into-lx-final-state, discard, or carry forward to lxw
3. `tar czf ~/Archive/lx-vault-2026-05-16.tar.gz -C ~/Library/Mobile\ Documents/iCloud~md~obsidian/Documents lx`
4. Verify tarball: `gzip -t`, `tar tzf | wc -l` matches original file count, sample-extract a known file
5. Do NOT delete `lx/` yet — wait until Phase 3

### Phase 1 — Bulk-import (engine-excluded) (2-3 hours)

6. `mkdir lxw/imported/lx/` (lxw is git-tracked — this becomes a commit)
7. Copy `🌈 Company/`, `👤 Personal/`, `🤖 AI/`, top-level loose MDs, `📥 Inbox/`, `Archives/` into `imported/lx/` preserving structure (emoji folder names included — they break grep tooling but it's a sealed import folder, doesn't matter long-term)
8. Move excalidraw → `lxw/Excalidraw/imported-lx/`; PDFs → `lxw/raw/papers/imported-lx/` (note: papers folder is substrate-tracked; verify this is the right destination or use a separate sealed folder)
9. **Skip `Templates/`** — incompatible
10. Add `imported/` to `.wiki/config.yaml` `excluded_paths` so compile/flush/curiosity don't touch it
11. Single commit in lxw: `feat(import): cold-storage lx vault contents → imported/lx/`
12. Verify: `wiki compile --dry-run` confirms `imported/` not scanned; Obsidian Search finds imported content; Graph view shows it as orphan island (expected)

### Phase 2 — Schema-driven migration (depends on prerequisites)

Prerequisites (each its own milestone or shipped feature):
- `archives-flag.md` — needed for the 5 lx-Archives + cold strategy docs
- `areas-bucket.md` — needed for ~6 force-fit Project candidates that are really Areas
- `entity-pages-state-timeline.md` — needed for the bulk of `imported/lx/🌈 Company/` and the strategy docs

When all three shipped, run migration:
13. Per entity in `imported/lx/`: extract State (current truth) + Timeline (when was it written, what happened), classify as person/project/concept/area, write to correct `knowledge/{...}/` location with two-layer shape
14. Cross-link liberally — many imported docs reference existing lxw entities (Yesterday people already in `knowledge/people/`, openclaw concept may already exist)
15. Verify each migration via `wiki query --include-archived` round-trip
16. Operator-driven, not LLM-automated — these are strategic docs, judgment-heavy

### Phase 3 — Cleanup (1 hour)

17. Verify all valuable content migrated out of `imported/lx/` (manual sweep + `find imported/lx -name "*.md" | wc -l` getting close to zero)
18. Decide: delete `imported/lx/` entirely, OR archive remaining low-value items to `knowledge/archives/` per archives-flag, OR keep `imported/lx/` permanently as sealed reference
19. Once `imported/` is empty/decided: remove from `excluded_paths` in config (if folder is gone)
20. `rm -rf ~/Library/Mobile\ Documents/iCloud~md~obsidian/Documents/lx` (cross-vault DESTRUCTIVE — explicit operator confirmation required, also verify tarball one more time)
21. DECISIONS.md entry: "lx vault dissolved YYYY-MM-DD, see commit X for migration map, tarball at ~/Archive/"
22. Memory cleanup: update `project_lxw_vault_path.md` if it implies lx-existence

## Touchpoints

- `lxw/imported/lx/` (new, Phase 1; possibly removed in Phase 3)
- `lxw/Excalidraw/imported-lx/`, `lxw/raw/papers/imported-lx/` (Phase 1)
- `lxw/.wiki/config.yaml` — `excluded_paths` extension (Phase 1)
- `scripts/core/config.py` + `migrations/migrate_config_keys.py` — IF `excluded_paths` doesn't exist as a config key yet, add it (must be same-commit per project hard-rule)
- `~/Archive/lx-vault-2026-05-16.tar.gz` (Phase 0)
- `lxw/knowledge/{people,projects,concepts,areas,archives}/...` (Phase 2 destinations)
- DECISIONS.md entry (Phase 3)
- `~/Library/.../lx/` — destroyed in Phase 3

## Lift estimate

- Phase 0: 1 hour (mostly verification)
- Phase 1: 2-3 hours
- Phase 2: blocked on 3 prerequisite milestones (~5-7 days each)
- Phase 3: 1 hour

**Phase 0+1 can ship today** (provides Single-Vault sanity immediately, decouples from prerequisite milestones). Phase 2 lands incrementally as prerequisites complete. Phase 3 closes the arc.

## Risks

1. **Phase 1 import bloats lxw git** — `Yesterday.excalidraw` is 4MB, `Yesterday(1).excalidraw` is 11MB. Mitigation: gitignore `imported/Excalidraw/*` (these aren't text, no diff value, tarball has them). Or LFS — overkill for personal vault. Recommend gitignore.
2. **iCloud sync conflicts during copy** — copying multi-MB files between two iCloud-synced folders can race with iCloud sync. Mitigation: pause iCloud sync during Phase 1 if observed; or `rsync` with `--ignore-existing` for re-runnability.
3. **Operator changes mind about lx after Phase 1** — `imported/lx/` is still git-tracked in lxw; reverting means a removal commit, no data loss (and tarball is canonical).
4. **Phase 2 schema-migration is heavy** — depends on 3 prerequisite milestones that may themselves take weeks. Mitigation: Phase 1 is the immediate win; Phase 2 is "do when ready", no time pressure. Operator can live indefinitely with `imported/lx/` as a sealed reference dump.
5. **Tarball single point of failure** — Mitigation: after Phase 0, copy tarball to second location (NAS, external drive, B2). Operator preference.
6. **Pre-tool-use hook conflicts with cross-vault writes** — llm-wiki has a pre-tool-use-edit hook that blocks Write/Edit in vault paths during certain agent contexts. Verify in Phase 0 before attempting Phase 1.

## Prior-art findings (from operator's 2026-05-02 own plan)

After Phase 1 shipped, operator's own pre-merge plan was discovered at `imported/lx/plan/vault/lx-lxw-merge.md` + `vault-architecture.md` + `vault-architecture.excalidraw`. Three operationally relevant findings absorbed back into this plan:

1. **iCloud-sync xattr trick for `.wiki/.venv/`** — `xattr -w com.apple.fileprovider.ignore#P 1 .wiki/.venv` excludes the Python venv from iCloud sync. lxw's `.wiki/.venv/` is **395 MB** (verified 2026-05-16); without this xattr, every venv-internal file syncs to iCloud. Set 2026-05-16 during Phase 1 sweep; behavior verification (iCloud daemon actually stops upload) pending observation. Generalizes: any `.venv/` inside an iCloud-synced vault should get this xattr.

2. **iCloud-sync discipline for Phase 3** — operator's plan explicitly said "1 Tag warten, parallel beide Vaults nicht öffnen" before final archive. iCloud Sync-Konflikte are real during multi-vault operations. Apply to Phase 3 (cleanup `rm -rf lx/`): close Obsidian on both vaults, wait for iCloud upload-status to settle, verify tarball one more time, then delete.

3. **state.json migration warning** (DO NOT) — operator's plan flagged "wenn `state.json` nicht mit-übernommen wird: spurious Recompile aller 347+ Artikel = ~$3-5 + Stunden". Does NOT apply to current direction (lxw-as-host, we don't move state). DOES apply if direction ever reverses (lx-as-host) — operator already explored that path 2 weeks ago, premise (PARA stays active) was empirically falsified, but the warning stays valid as a hazard if revisited.

Architectural observation: operator's plan was the **opposite direction** (lxw → lx, with `.wiki/` newly installed in lx as a layer on top of PARA). That direction was implicitly abandoned over the following 2 weeks as collector-driven capture (voice, jamie, gmeet, email, calendar, health) replaced PARA's filing-cabinet function. The fact that operator stopped maintaining lx is the empirical signal that the two-layer "PARA + Wiki" architecture lost to event-stream-driven capture. Current direction (lxw-as-host) is consistent with that signal.

The one gap operator's plan implicitly covered (long-form deliberate human writing — strategy workdocs, manifestos, opinion essays) is NOT yet covered by lxw. Surfaced as new backlog item `compile-role-axis.md` (Phase 2 prerequisite, recommended replacement for `archives-flag.md`).

## Ripens when

- Operator says "go" on Phase 0+1. Already validated demand.
- Phase 2 ripens incrementally as prerequisites ship.

## Status

Phase 0 ✓ (tarball `~/Archive/lx-vault-2026-05-16.tar.gz`, verified). Phase 1 ✓ (cold-storage commit `cf8db73` in lxw vault repo). Phase 2 blocked on prerequisites. Phase 3 blocked on Phase 2.

**Prerequisites for Phase 2** (revised after compile-role-axis emerged):
- `compile-role-axis.md` — generic engine-skip / index-only / distill axis; absorbs `archives-flag.md`
- `areas-bucket.md` — 7th knowledge bucket for ongoing responsibilities
- `entity-pages-state-timeline.md` — gbrain pattern for the bulk per-entity migration

Related: `archives-flag.md` (subsumed by compile-role-axis; mark as historical), `areas-bucket.md`, `domain-frontmatter.md`, `entity-pages-state-timeline.md`, `gbrain-comparison.md`.
