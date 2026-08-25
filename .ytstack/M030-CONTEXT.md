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

(none — all seven slicing questions resolved 2026-08-25 as engine-side defaults, see decisions above; operator may veto any of them before the affected task runs)

## Defaults decided at slicing (2026-08-25, operator veto possible)

- Slugs: bare kebab-case, no `lw-` prefix (readability; the server already rejects cross-wiki slug collisions with the owning wiki named — surfaced as errors, deterministic local collision check on top).
- Wikilinks: normalize via the existing `core.links` resolver; unresolvable targets and targets outside `knowledge/` degrade to plain text (compile policy already bans body links to raw/ + daily/, so this is the rare-edge posture, not the common case).
- Descriptions: `knowledge/index.md` summary row (full-index row parse — the compact loader strips the summary column), fallback first body paragraph, hard-capped 1024.
- `knowledge/index.md` itself is EXCLUDED from the publish set (inventory table would flood server FTS without persona value; the generated start page replaces it as entry point).
- Slugs must be FIXPOINTS of the server-side `slugifySkillName` re-slugification (NFKD fold, lowercase, `[^a-z0-9]+`→`-`, hyphen-trim, 120-char cap), else retraction ids diverge — unit-tested.
- Cadence: explicit `wiki publish` (S02) + compile piggyback via a proper `piggybacks.publish` table entry (S03; no separate bool knob).
- Token: SUPERSEDED 2026-08-25 (operator catch: no producer-token mint documented upstream; the Keychain `MEINKONTEXT_TOKEN` from MCP-CONNECT.md is an org api-key = READ-ONLY, write tools are user-principal only, user JWTs short-lived). New default: `wiki publish --auth` — one browser consent (DCR public client, PKCE S256, scope `offline_access`; refresh-issuance verified in the vendored oauth-provider), tokens at `STATE_DIR/meinkontext-oauth.json` (google_oauth cache convention), headless refresh with rotation. `MEINKONTEXT_TOKEN` env demoted to explicit user-token override. (S02-T06)
- Start page: small generated overview article (MOC links + counts) with `start_page: true` — index.md is too large to serve as entry page.
- Secret-gate rejects: fail-soft — skip article, WARNING in errors-log, run continues (matches compile's per-item posture).
