# Setup: wiki publish — the meinkontext remote mirror

`wiki publish` maintains a managed wiki on the operator's meinkontext
(context-mcp) server as a **one-way mirror** of the vault's markdown. The
vault stays the only source of truth; the server is registry + delivery.
Binding contract: `docs/PRODUCER-CONTRACT.md` in the context-mcp repo — on
disagreement, its REFERENCE PRODUCER RUN test wins.

## What publishes

Every markdown file under the configured `publish.roots` (vault-relative
folder names). Engine default is `["knowledge"]` — the curated wiki. The
ALLES posture (operator decision 2026-08-25: "Substrat und Destillat gehören
zusammen") adds the substrate:

```yaml
publish:
  enabled: true
  endpoint: https://<your-context-mcp>/mcp
  wiki_slug: llm-wiki      # stable identity — never rename after first publish
  wiki_name: LLM Wiki
  roots:
  - knowledge
  - raw
  - daily
  - reports
  - workspace
```

Hard boundaries:

- **Markdown-only** (contract: one markdown file per article). Binary/JSON
  assets (pictures, audio, request JSONs) have no channel and are counted in
  the dry-run as `non-markdown files … not published`.
- `knowledge/index.md` is excluded (a generated start page with MOC links
  replaces it as the wiki entry point).
- The **server secret gate** rejects articles containing secret-shaped
  values (key blocks, `sk-` prefixes). Rejects are per-article fail-soft:
  skipped, WARNING-logged, listed in the report — sanitize the article
  locally or accept it staying local-only.

## One-time connect

1. `wiki config set publish.enabled true`
2. `wiki config set publish.endpoint https://<your-context-mcp>/mcp`
3. `wiki publish --auth` — one browser login + consent. The producer
   registers as an OAuth public client (DCR, PKCE S256) with scope
   `offline_access`; access + refresh tokens land in
   `.wiki/state/meinkontext-oauth.json` and refresh headlessly from then on
   (including mid-run — access JWTs expire in under an hour, a first full
   publish runs longer).

Token notes:

- The write tools are **user-principal only**: the org api-key from
  context-mcp's MCP-CONNECT setup is read-only and cannot publish.
- `MEINKONTEXT_TOKEN` in `.claude/.env` is an explicit override only (must
  be a user token). CAUTION: the vault iCloud-syncs — prefer a
  Keychain-backed shell export (`security find-generic-password …`) if you
  use the override at all.

## Publishing

- `wiki publish --dry-run` — the full plan (create/update/retract per
  article, per-corpus totals, non-markdown count). Review this before the
  first live run.
- `wiki publish` — sequential execution. Idempotent by content hash: an
  unchanged rerun performs zero writes. Transient 5xx (the server redeploys
  on every merge) are retried with backoff; progress persists per article in
  `.wiki/state/publish.json`, so an aborted run resumes where it stopped.
- Deleting a file locally **archives** the article upstream on the next
  publish (auditable history, never a hard delete); re-creating the file
  restores it with its version history continuing.

## Cadence

`piggybacks.publish` (default: enabled, cooldown 6 h) fires `wiki publish
--piggyback` from the compile/flush piggyback drain, keeping the mirror
fresh after the operator's normal loop. On vaults with `publish.enabled:
false` the fire is a designed quiet no-op.

## Verifying

`get_status` from any connected MCP client echoes the wiki (`wikis:
[{slug, articles, managed_by}]`), storage, and versions. The dashboard shows
the managed wiki with a "published by llm-wiki" badge — change content in
the vault, read it there.
