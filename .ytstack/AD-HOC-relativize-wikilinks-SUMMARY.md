# AD-HOC: Wikilinks relative to their containing article (2026-05-29)

## Trigger
Operator screenshot: clicking cross-article links in Obsidian created empty `.md`
stubs. Reported "die knowledge artikel untereinander sind falsch verlinkt, da
müsste immer ein ../ davor".

## Root cause
Engine wrote knowledge-internal links as `[[concepts/foo]]` — a path relative to
`knowledge/`, not the article — on the false assumption (baked into `lint.py`
comment + `backlinks.py` + `utils.wiki_article_exists`) that "Obsidian resolves
`[[concepts/foo]]` against any indexed dir". Reality: Obsidian resolves a **bare**
name shortest-path, but a **slash-bearing** link is a path tried **source-relative
AND vault-absolute** (`<vault>/`, where `.obsidian/` lives). From a nested
`knowledge/<type>/x.md` both bases miss → empty-stub-on-click. `daily/`+`raw/`
worked only because they are real top-level folders; `index.md`'s links worked
because it sits directly in `knowledge/` (source-relative hit). 18.5k links
across 1.7k articles affected.

## Decision
Links are stored **relative to their containing article** (operator-directed:
"es muss IMMER relativ zur markdown file sein"). Same-bucket `[[foo]]`, cross
`[[../people/alex]]`, substrate `[[../../daily/d.md]]`. Authors write the
unambiguous `[[knowledge/<type>/<slug>]]` form; a deterministic post-compile pass
relativizes — LLMs compute relative paths unreliably, so authoring is decoupled
from on-disk correctness. Full rationale: DECISIONS 2026-05-29.

## Shipped (commit 4b4eb5b — relativize fix)
- `scripts/core/links.py` (new) — single resolver: `resolve_link`,
  `canonical_slug`, `relativize_text`, `run_relativize_pass`, `link_target`,
  `relative_link_for_slug`. Resolves each link against the real filesystem;
  rewrites relative; **never fabricates a path** (unresolvable → left untouched).
- `scripts/core/backlinks.py` — index keyed on canonical slugs (resolves +
  drops substrate edges); footers rendered relative per article.
- `scripts/lint.py` — `check_broken_links` / `check_missing_backlinks` /
  connection-endpoint count resolve source-relative; `count_inbound_links`
  (utils.py) resolves instead of literal-matching; dead `wiki_article_exists`
  removed.
- `scripts/compile.py` — relativize pass wired after the backlinks pass, gated
  by `features.relativize_wikilinks` (default True; config + migration added).
- `scripts/migrations/relativize_wikilinks.py` — one-shot corpus migration CLI.
- Docs: `AGENTS.md` (Wikilinks convention §), `prompts/compile_main.md`,
  DECISIONS, KNOWLEDGE.
- Tests: `test_links.py` (new), `test_backlinks.py` (rewritten + cross-folder
  footer regression guard).

## Shipped (commit 09d2097 — broken-link tooling)
- `scripts/links_audit.py` + `wiki links` / `wiki links --fix` — categorized
  broken-link report (media / placeholder / dangling) + approval-gated fixer.
  Tiers: ≡ exact-basename-different-bucket (near-certain), ~ fuzzy (cutoff 0.85,
  eyeball). `--yes` applies ≡ only. Missing-article refs never auto-fixed.
- `wiki` (cmd_links + dispatch + header), `docs/cli.md`,
  `tests/test_links_audit.py`.

## Verification
- Corpus migrated on lxw: **17.346 links → relative**, idempotent re-run = 0
  (proof every rewritten link resolves: `relativize_text` only rewrites a link
  whose target it located on disk). 17.629 resolved corpus-wide.
- Obsidian resolves the relative form — **operator clicked** `[[../people/alex]]`
  etc. before the full migration (the one engine-untestable fact).
- backlinks pass on lxw: relative footers, pass2 = 0. Compile chain
  (backlinks→relativize) settles to 0.
- `wiki links` runs end-to-end through the installed dispatcher in lxw after
  `wiki update` (operator confirmed). `wiki links --fix` round done by operator
  — "war gut".
- Full suite 1112 passed (4 pre-existing `test_dream_sampling` failures verified
  on clean HEAD — unrelated, another session's WIP).

## Open / deferred
- **92 missing-article refs** — genuine dangling targets (never-created concepts,
  e.g. `concepts/test-driven-development`, `people/timo-fey`). Operator task:
  create via compile/dream or drop. `wiki links` surfaces them.
- **`raw/notes/longform/` source-and-final pages** — the relativize pass is
  knowledge-only, so longform docs' internal `[[concepts/…]]` links are NOT
  relativized and break the same way from `raw/`. See
  `.ytstack/backlog/relativize-wikilinks-followups.md`.
- Relativize pass firing **during a real `wiki compile`** not yet observed
  in-context — confirms via the `relativize pass: …` log line on next compile.
