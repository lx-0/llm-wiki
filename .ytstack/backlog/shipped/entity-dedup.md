# `wiki dedup` — interactive entity deduplication for transcription-noise duplicates

**Source pitch:** GitHub issue [#3](https://github.com/lx-0/llm-wiki/issues/3) (@Sidwach, field request from a second operator vault).
**Size:** M (one milestone, ~4 slices). **Cloud cost:** none ($0, deterministic detection; LLM only optional). **Status:** open — implementation started 2026-05-31 as an ad-hoc arc.

## Problem

STT transcribers (Jamie, voice) introduce *consistent* spelling noise that creates **silent duplicate** entity pages in `knowledge/people/` and `knowledge/projects/`:

- `josefine-bartsch.md` vs `josephine-bartc.md` — same person, German name with ambiguous phonetics.
- `veltari.md` (a real company) vs `veltary.md` (a phantom entity the transcriber invented — doesn't exist).

Consequences: split knowledge (Action Items / Timeline spread across two pages), phantom wikilink targets that look real, and compile-loop contamination (the LLM builds on the wrong name in future passes). The operator discovers these manually while browsing — no systematic detection, no guided cleanup.

This is **structural, not accidental**: every voice-heavy vault accumulates them. A one-off manual pass doesn't scale.

## Design

### Detection — stdlib-only, $0, deterministic

Scan `knowledge/{people,projects,areas}/*.md`. Score each candidate pair on three signals:

1. **Fuzzy string distance** — `difflib.SequenceMatcher.ratio()` on normalized slugs/titles + `aliases:` frontmatter. (Stdlib; no `rapidfuzz`/`jellyfish` dependency added — keeps the engine lean and the detector unit-testable without a C extension.)
2. **Phonetic key match** — a hand-rolled **German-aware** phonetic normalizer (collapse double letters, `ph→f`, `v→f`, `c→k`, `tz/z→ts`, `sch→s`, `th→t`, strip accents + trailing `-e/-h`). Two titles "match" when their phonetic keys are equal or near-equal. Deliberately NOT Soundex/Metaphone — those are English-vowel-biased and underperform on the real failure mode (German names like *Bartsch/Bartc*).
3. **Shared `compiled_from` sources** — two pages citing the same raw transcript are a strong duplicate signal (boost).

Output: ranked `(slug_a, slug_b, confidence, reason)` pairs. Threshold via `limits.dedup_fuzzy_threshold` (default `0.85`).

Keep a slow O(N²) pair-scan ONLY behind a small-N guard — index by phonetic key first (`{key: [slugs]}`), then only fuzzy-compare within-bucket + cross-source pairs. (Per CLAUDE.md O(N²) hard-won rule: per-item-over-all-items is latent O(N²); 1700-entity vaults would hang. Bucket once, compare within bucket.)

### Interactive Q&A loop (`wiki dedup`)

Per candidate pair, walk the operator through: same entity? → which name is correct (A/B/type-in)? → merge? Every merge requires **explicit** confirmation — never automatic. `--dry-run` shows what would happen without writing.

### Merge operation (on confirm)

1. Append B's `## Timeline` entries to A (chronologically sorted, source attribution preserved).
2. Merge B's `## Action Items` / `## Open Threads` into A (dedup by content).
3. Union B's `compiled_from:` into A's frontmatter.
4. Union B's title + `aliases:` into A's `aliases:` (so future compiles recognize the variant).
5. Delete B's file (`.bak.<ts>` kept — never a hard `rm`).
6. Rewrite every `[[wikilink]]` across `knowledge/` pointing at B → A. **Reuse `core/links.py`** (`resolve_link` / `canonical_slug` / `relative_link_for_slug`) — do NOT hand-roll a second wikilink rewriter (write-read-symmetry rule). Rewrites must be idempotent.
7. Auto-create a canonical-name hard fact via `facts/correct.py` (`status: negation`, `--term "Josephine Bartc"`), so lint flags any future reappearance.

### Modes

- `wiki dedup` — detect + interactive loop (default).
- `wiki dedup --suggest-only` — print candidate list, no loop (quick "what needs cleanup?").
- `wiki dedup --dry-run` — walk without writing.
- `wiki dedup merge <B> --into <A>` — standalone known-pair merge (skip detection, confirm + execute).

### Optional lint surfacing

`check_entity_fuzzy_duplicates` in `lint.py` (warn, not error) flags the same candidate pairs in the lint report, pointing the operator at `wiki dedup`. Add to the structural `checks` list. Low priority — the detector is the load-bearing part.

## Affected files

- `scripts/dedup.py` — new: detection + merge logic (stdlib-only detection).
- `wiki` — new `dedup` subcommand (`cmd_dedup` + dispatch entry + help block) wrapping `_run_script dedup.py`; refresh dashboards after a merge (mirrors `cmd_correct`).
- `scripts/core/config.py` — `Limits.dedup_fuzzy_threshold: float = 0.85`.
- `scripts/migrations/migrate_config_keys.py` — add `limits.dedup_fuzzy_threshold` to `KEY_ADDITIONS` (same commit — config-change rule).
- `scripts/facts/correct.py` — reused (programmatic `cmd_add` or shell-out) to register the canonical-name hard fact.
- `scripts/core/links.py` — reused for the wikilink rewrite (no new resolver).
- `scripts/lint.py` — optional `check_entity_fuzzy_duplicates` (warn tier).
- `tests/` — detector golden tests (German STT pairs), merge idempotence, wikilink-rewrite correctness.
- `docs/architecture.excalidraw` + `docs/overview.excalidraw` — fold `wiki dedup` into the maintenance/lint band (steady-state portrait, no milestone badge).

## Relationship to existing systems

- `wiki correct` — the merge calls it to record canonical-name hard facts; dedup is the detection + interactive UI layer on top.
- `wiki reconcile` — handles fact violations *within* existing articles; dedup handles the case where two separate articles shouldn't exist at all. Complementary, not overlapping.
- `wiki links` — `links_audit.py` already rewrites dangling refs; dedup's merge rewrites *valid* refs from B→A. Share the `core/links.py` resolver, different trigger.

## Open questions / risks

- **Destructive merge** — file-delete + corpus-wide wikilink rewrite. Hard guardrails: `.bak.<ts>` on delete, idempotent rewrites, `--dry-run`, mandatory per-pair confirmation. No `git rm`, no unconfirmed batch merge.
- **Phantom vs real** (Veltari/Veltary) — the operator decides; the tool surfaces the pair + lets them pick the correct name (or reject the pair). Phantom-detection is not automated.
- **Slug `default` / reserved names** — none here; entity slugs are free-form.
