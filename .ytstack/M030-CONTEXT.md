---
milestone: M030
project: llm-wiki
created: 2026-08-25T06:49:07Z
size: M
---

# M030 -- Context

## Goal

Every `knowledge/` article and hard fact is readable by the operator's agents anywhere via meinkontext: `wiki publish` maintains a managed wiki there as a one-way, idempotent mirror of the compiled corpus (lane D of `.ytstack/OFFICE-HOURS-remote-mcp-access.md`).

## Exit criteria

1. `wiki publish` creates the managed wiki once (`create_wiki`, `managed_by: "llm-wiki"`) and publishes ALL `knowledge/` articles per `docs/PRODUCER-CONTRACT.md` (context-mcp repo, v1/v0.0.56); a second run with no local changes performs ZERO writes (content-hash state in `.wiki/state/`).
2. Full lifecycle proven against the live dev server, mirroring the REFERENCE PRODUCER RUN (`wiki-tools.test.ts:266`): publish → update (new version_seq) → local delete archives upstream on next publish → re-added slug restores.
3. Live end-to-end proof: a Claude session on another machine (or claude.ai custom connector), grounded only via meinkontext, answers a personal-context question from a published article — with the Mac allowed to sleep afterwards.
4. Engine discipline held: config knobs + migration entries in the same commit; publish reads only `knowledge/` and writes only `.wiki/state/` + logs (never raw/, daily/, workspace/); PROCESS.md + docs/config.md + both infographics updated in the same arc; suite green.

## Size

M -- see `M030-ROADMAP.md` for slice breakdown.

## Decisions locked in discuss phase

- 2026-08-24: Lane D chosen — llm-wiki stays local producer + source of truth; meinkontext is the delivery layer (its Knowledge-KB path (b); llm-wiki is the contract's named first consumer). Approach B (own public endpoint) superseded; A (tailnet `wiki serve`) deferred until a concrete deep-access need appears.
- 2026-08-25: Gate width = ALLES — full `knowledge/` export, no sensitivity/scope subset filter. The only boundary is `knowledge/` itself; raw/, daily/, workspace/ never leave (locked prior decisions + contract-infeasible anyway: markdown-only, secret gate, 100 MB quota). `sensitivity:` frontmatter stays marking-only and passes through verbatim.
- 2026-08-25: `docs/PRODUCER-CONTRACT.md` (context-mcp) is the binding contract; on disagreement its executable twin (REFERENCE PRODUCER RUN test) wins. Idempotency is OUR job (local content-hash diff); server versions every write @stable.
- 2026-08-25: Auth = operator-scoped OAuth token per the live-import runbook (`docs/setup/MCP-CONNECT.md` there); no per-producer identity exists in v1 — `managed_by` is cooperative, not enforced.

## Open questions

- Slug mapping: `knowledge/<type>/<name>.md` → flat global kebab-case slug. Prefix (`lw-`?) vs bare slugs; deterministic collision policy (slugs are unique across the WHOLE meinkontext catalog, not just our wiki).
- Wikilink normalization: links are stored relative-to-file (core.links resolver) — normalization to `[[target-slug]]` must reuse that resolver; behavior for links whose target is outside knowledge/ (raw/, daily/) → drop, plain-text, or leave dangling?
- Per-article `description` (required, ≤1024): source from the article's `knowledge/index.md` summary row (preferred, zero new LLM cost) — fallback when an article has no index row?
- Publish cadence: compile piggyback (piggybacks.py pattern, cooldown-gated) vs explicit `wiki publish` only for v1?
- Token bootstrap UX: where the OAuth token lives (`<vault>/.claude/.env` key name) and how the operator mints it (runbook pointer vs guided flow).
- `start_page: true` target: generated landing page vs an existing MOC (index.md is too large to be the entry page).
- Secret-gate rejects (server-side scan): skip-and-report per article vs abort run.
