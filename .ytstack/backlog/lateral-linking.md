# Lateral Linking — Tag-Jaccard "Related" sections for concepts/ — REJECTED

**Status (2026-05-15):** Rejected, not deferred. Working implementation lived in `scripts/links/lateral.py` for half a session and was discarded before commit.

**Why rejected:** The audit that motivated this proposal was buggy. The original grep counted only bare `[[slug]]` wikilinks and missed `[[concepts/slug]]` form — which is what `compile.py` actually emits in its `## Related Concepts` sections. The "0 lateral links" claim was wrong; the real count is **5392 lateral concepts→concepts links** (77% of all wikilinks from concepts/). 686 of 873 concepts already carry hand- or LLM-curated Related sections.

**What this means:** The graph-view "hairball" perception is not a missing-edge problem. It's a force-layout problem: 8-10 mega-hub notes (`projects/fleet`=150 backlinks, `agentisches-manifest`=69, `symptom-vs-root-cause-discipline`=81, ...) gravitationally dominate the layout regardless of how many lateral edges exist. The truth in the data is "everything is densely interconnected because the operator's disciplines apply across all domains" — themed-island visualization fights that truth.

**Lessons recorded in KNOWLEDGE.md:** audit-before-implementing rule (next entry).

The original concept below is preserved for record but DO NOT implement it without first re-verifying the lateral-edge audit.

---

## Original concept (for record only)

A deterministic post-processing pass that adds a `## Related` section (between markers) to every `concepts/*.md` note, listing the top-K most thematically similar concepts ranked by tag Jaccard similarity. No LLM call, no embedding stack — runs offline against the existing tag layer.

## The problem

Audit on 2026-05-15: 6743 Wikilinks from `concepts/`, **0 of them to other concepts/**. Every concept-note points "outward" — projects, people, MOCs, connections — never sideways. Force-directed graph layout can only cluster what has edges. Without lateral edges, every theme dissolves into a star around its dominant hub note (`projects/fleet` = 165 backlinks).

Concept tags carry the missing signal already: 968 notes with avg 5.2 tags each, dense overlap (fleet ↔ openclaw = 75 shared notes, claude-code ↔ plugins = 31, …). A Jaccard score over tag sets is enough to surface "topically near" concepts without an embedding model.

## What changes

Each `knowledge/concepts/<slug>.md` gets a marker-delimited block appended (or in-place updated):

```markdown
<!-- LATERAL-LINKS-START -->
## Related

- [[concepts/fleet-manager-patterns]]
- [[concepts/agent-config-staleness]]
- [[concepts/openclaw-bot-self-sabotage-patterns]]
- [[concepts/symptom-vs-root-cause-discipline]]
- [[concepts/audit-before-declaring-done]]
<!-- LATERAL-LINKS-END -->
```

The block is **idempotent**: re-running the pass replaces the inside, never touches anything outside the markers. Operator-curated edits inside the block survive only if the pass produces the same set; otherwise they're regenerated. Operator-curated edits *outside* the markers (rest of the note body) are never touched.

## How the math works

For two concept notes A and B:

```
jaccard(A, B) = |tags(A) ∩ tags(B)|  /  |tags(A) ∪ tags(B)|
```

Range 0..1. Empty tag set → score 0. Identical tag sets → 1.

For each concept, compute jaccard against all other concepts, keep top-K with score ≥ threshold, skip the note itself, skip notes already wikilinked elsewhere in the body (to avoid duplicate edges via the index plus this list).

Expected output on lxw vault:
- 840 concepts × ~5 related each ≈ **~4000 new edges**
- Coverage: notes with rare tag combinations (1 tag, no overlap) get an empty Related section → still gain a section header, just no entries. That's fine — explicit "I tried, found nothing" beats silent skip.

## Why not LLM / embeddings

- **LLM**: hallucination risk (proposes "related" notes that don't exist or aren't really related), cost ($30+/full pass on 840 notes), nondeterministic re-runs.
- **Embeddings**: requires a model + dependency + persistence layer (vector cache), adds operational surface. The tag layer already encodes operator judgment about *what a note is about* — using it directly is the cheaper signal that's also more interpretable.
- **Trade-off accepted**: tag-Jaccard is "topical, coarse" not "semantically deep". Two notes about completely different topics that happen to share `discipline + claude-code + workflow` would surface as related. Mitigation: domain tags now mandatory (commit `da23f2b`) raises the floor — domain co-membership is a real signal, not just generic-tag-noise.

## Integration

### New module: `scripts/links/lateral.py`

Topology mirrors `scripts/suggestions/` and `scripts/facts/` — sub-package with `__init__.py`, single primary entry point. Reads CONCEPTS_DIR, computes scores in pure Python, writes back via marker-delimited replace.

Public API: `apply_lateral_links(dry_run: bool = False) -> dict[str, int]` — returns `{slug: edge_count}` for reporting. CLI dispatcher wraps it.

### CLI: `wiki link`

```bash
wiki link --dry-run    # show what would change, write nothing
wiki link apply        # write the Related sections
wiki link              # same as --dry-run by default (safety)
```

Mirrors `wiki correct` two-step shape (dry-run by default, explicit `apply`).

### Config tunables (`scripts/core/config.py` + `config.example.yaml`)

New `LateralLinks` dataclass under `WikiConfig`:

```python
@dataclass
class LateralLinks:
    top_k: int = 5             # max Related entries per concept
    min_jaccard: float = 0.25  # below this, drop the candidate
    show_scores: bool = False  # append "(jaccard 0.42)" to each line — useful for tuning
    skip_existing_wikilinks: bool = True  # don't add a Related entry if the body already wikilinks that target
```

### Lint interactions

- `check_broken_links` already runs over every wikilink; new Related-section links are subject to it. Free coverage.
- `check_orphan_pages` counts inbound links across all articles — Related sections push orphan-counts way up, so existing orphan warnings should drop after the first apply. Side benefit.
- No new check needed — the existing structural checks naturally absorb this layer.

### What it does NOT touch

- `compile.py` — entirely separate pass. No coupling. Compile runs, lateral runs, no order constraint other than "lateral after compile if you want fresh tags reflected".
- `qa/`, `connections/`, `people/`, `projects/`, `MOCs/`, `facts/` — out of scope. Connections are explicitly cross-domain; people/projects use the two-layer State+Timeline shape (M005-S01); MOCs are operator-curated; facts are operator-curated.
- Cross-folder links — `concepts/` ↔ `concepts/` only. Cross-folder edges already exist via the index and individual article bodies.
- Frontmatter — no schema change. Section lives in the body between markers.

## Edge cases & failure modes

1. **A concept has no tags.** → empty intersection with everything → empty Related section header appears, no entries. Lint already warns on missing tags (`check_concept_domain_tag`).
2. **All N matches have score < threshold.** → same as (1).
3. **Concept already has a `## Related` section without markers.** → pass treats it as operator content, appends a *new* marker-delimited block below. Operator can manually delete the old one. Alternative: detect header without markers and warn. Defer the warn-and-merge logic until it actually happens.
4. **Operator edits a link inside the markers.** → next run regenerates → edits lost. Documented in the section comment. Workaround: edit outside the markers; the marker block is engine-owned.
5. **A wikilinked target doesn't exist** (compile.py-emitted slug typo, etc.). → `check_broken_links` flags it. Lateral pass doesn't verify existence — that's lint's job.
6. **Performance**: 840 × 840 pairwise comparisons = 706k comparisons, each is two set ops. Python set arithmetic at this scale: << 1 second. No optimization needed.
7. **Apple-iCloud-sync collision during write** (lxw vault lives on iCloud Drive). Use `Path.write_text` not atomic-replace; concurrent partial writes would corrupt. Risk is low (operator-triggered, not auto-scheduled); document don't engineer for it.
8. **The dedup-against-existing-wikilinks check**: when `skip_existing_wikilinks=True`, scan note body (excluding the Related block!) for `[[concepts/X]]` and skip those targets. Must exclude its own marker block to avoid the trivial self-skip-on-rerun.

## Tunables — sensible defaults

- `top_k=5` — readable, fills a paragraph without bloat
- `min_jaccard=0.25` — empirically right for ~5 tags per note: requires ≥2 shared tags out of ~8 union. Tuning probe: run with `show_scores=true`, inspect a sample, adjust.
- `show_scores=false` — operator-facing surface is clean; scores only for debugging.

## Effect on the graph view

- Tag-Jaccard tends to cluster same-domain notes (same domain tag → high intersection) → mechanical theme islands form in the Force-directed layout.
- The 75 fleet+openclaw cross-domain notes will get edges to *both* fleet-cluster and openclaw-cluster members → spatial bridges between domains. That's the desired behaviour: cross-cutting notes visibly bridge.
- Mega-hub notes (`projects/fleet` etc.) keep their inbound-link gravity but no longer dominate the topology — concepts now have lateral attraction toward each other in addition to outward attraction to projects/people.

## Lift estimate

- `scripts/links/lateral.py` core algorithm + idempotent marker write: 0.5 day
- CLI dispatcher (`wiki link`) + help text: 0.25 day
- Config dataclass + example.yaml entry: 0.25 day
- First dry-run on lxw vault, sample inspection, threshold tuning: 0.5 day
- Apply pass + spot-check graph view: 0.25 day
- Tests (unit on jaccard + marker write idempotency): 0.25 day
- KNOWLEDGE.md + AGENTS.md: 0.25 day

**~2 days end-to-end.** Tighter than the initial estimate because no compile.py changes and no lint extension.

## Ripens

Now. The substrate is ready:
- Domain-tag rule landed (commit `da23f2b`) — concepts/ tag quality is enforced going forward
- Extended Graph plugin configured (Multi-Channel: shape=type + color=domain) is live in lxw
- The Force layout is responsive (`centerStrength: 0.1, repelStrength: 30, linkStrength: 0.2, linkDistance: 250`) — adding edges will produce visible reorganization

## Status

Active. Implementing now as a single arc (no slicing). Single commit when verified end-to-end against lxw.
