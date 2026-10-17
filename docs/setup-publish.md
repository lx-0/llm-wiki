# Setup: wiki publish — the meinkontext remote mirror

`wiki publish` maintains a managed wiki on the operator's meinkontext
(context-mcp) server as a **one-way sync** of original vault files plus searchable markdown articles.
The vault is authoring input; meinKontext's central database and S3 store serve the
published snapshot over MCP.
Binding contract: `docs/PRODUCER-CONTRACT.md` in the context-mcp repo — on
disagreement, its REFERENCE PRODUCER RUN test wins.

## What publishes

Every file under the configured `publish.roots` (vault-relative
folder names), including original markdown, binaries, JSON, hidden files and empty folders. Engine default is `["knowledge"]` — the curated wiki. The
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

Originals preserve their vault-relative paths, case, Unicode and exact bytes. Markdown
also has the existing searchable article projection; original files retain wikilinks,
frontmatter and line endings before that transformation. `knowledge/index.md` is included
as an original; the generated start article remains separate.

Symlinks, missing/unreadable roots and unsupported filesystem entries stop inventory.
The server secret gate applies to original bytes/path metadata and article projections.
Rejected files remain explicitly reported, and that run does not archive anything.
The only size limits are the existing organization quota and server request-body limit
(including base64/JSON overhead). No silent file-count or extension exclusions.

## One-time connect

Prerequisites: a running context-mcp (meinkontext) instance reachable over
HTTPS and a **user account** on it — the browser consent in step 3 signs in
as that user, and only user principals may write. An org api-key from the
MCP-CONNECT setup is not enough (read-only). The server must support producer contract v3 (`write_wiki_file`,
`move_wiki_files`, `write_article.source`); an older server is refused before writes.
`wiki publish` creates the managed wiki on first run.

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

## Publishing and first adoption

Keep publishing disabled while reviewing the destination and inventory. Preserve a private
copy of `.wiki/state/publish.json`, a consistent vault snapshot, and the destination's
backup/recovery receipt before first adoption. Dry runs work while disabled and write
neither the journal nor the server.

- `wiki publish --dry-run --json`: review article changes and original-file counts,
  paths and byte totals for every configured root.
- `wiki publish --backfill --dry-run --json`: only new original bindings for existing
  manifest articles. After approving that diff, `wiki publish --backfill` executes it
  without new article versions, start-page edits or archives.
- `wiki publish`: synchronize the remaining originals and article changes. Each source
  has a stable key, expected remote revision and durable operation ID. Original read-back
  must match its SHA-256 before the private journal advances. An unchanged run has no
  writes. Original and changed article commit together; conflicts roll both back.
- `wiki publish --move 'old/path.md=new/path.md'`: reconcile a move already made in the
  vault. Repeat the flag for a path swap; directories expand their known child paths.
  Source identity and article slug survive; copies get new identities. A completed batch
  may be repeated safely. Equal content never silently becomes move evidence.
- Additions alongside removals keep deletions pending, including in later runs. Reconcile
  moves or review the diff and pass `--confirm-deletions` for genuine removals. Deletion
  archives history rather than purging it. Reappearing files restore the same identities.
- Changing configured roots requires `--accept-scope-change` after reviewing the dry run.
  Missing roots, changed inventories and rejected uploads never justify retractions.

Only one local run holds the journal lock. After a lost response, rerun the same command
with unchanged input: durable receipts prevent duplicate revisions. If a pending source
changed, the run stops for reconciliation. Preserve the journal and restore the interrupted
input from the private snapshot before replay; never discard pending operations to force
progress. `last_source_run` records running/complete/incomplete and counts. A crash may
leave running; that is interrupted, not success. Atomicity is per file, not a global vault
snapshot. Transport retries and token refresh use the existing MCP client.

To undo a path batch, use its saved before/after mappings and returned revisions in an
inverse `move_wiki_files` request with new operation IDs. `expected_revision` rejects
intervening writes; never force an old mapping over newer content. Preserve the confirmed
inverse receipts in a private journal recovery copy before resuming. Rolling application
code back leaves the additive server schema/data in place; no whole-store restore or
wiki deletion/recreation is part of a path rollback.

## Verifying originals

`get_wiki(view: files)` lists original metadata and `wiki-source://file/<id>/<revision>`
read links under live access. A stale URI is refused; list again. In meinKontext, the wiki
Files tab and global Explorer show the same read-only source tree. Edits happen in the
source vault. Relative links resolve inside accessible wiki files; embeds never load
active or external content automatically.

**Export original files** returns the original paths, bytes and empty directories plus
`_meinkontext-export.json` (numbered if occupied). Verify lengths and hashes against the
private source snapshot and remote read-back. Generated/unmapped legacy articles stay
available through the ordinary export. Portable path collisions fail explicitly instead
of overwriting or silently renaming files. Later files follow a shared wiki's live
container link; revocation denies reads and exports.

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
