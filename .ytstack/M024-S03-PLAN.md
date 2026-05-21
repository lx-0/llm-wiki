---
milestone: M024
slice: S03
status: planned
created: 2026-05-21
---

# M024-S03 — Template resync · docs · lxw E2E

## Tasks

- [ ] T01 — template + docs resync
  - `templates/` config template (if it carries a gmeet example) gains the
    `email_discovery` block. `docs/PROCESS.md` (and `docs/cli.md`/`FEATURES.md`
    if they enumerate gmeet) document email-discovery as a second discovery
    source for the gmeet collector.
  - Infographic: per the steady-state rule, fold "email-triggered discovery"
    into the existing gmeet box caption only if it earns a slot; otherwise
    PROCESS.md only. Decide against `docs/architecture.excalidraw`.

- [ ] T02 — lxw live E2E
  - Push first (engine→origin), then `wiki update` on lxw, then
    `wiki collect gmeet`. Verify: colleague-owned meetings (the 4 gemini-notes
    mails in INBOX, incl. chris@yesterday-ai.de) land in `raw/transcripts/gmeet/`
    with clean UTF-8; second run is idempotent (file-id dedup → 0 new).
  - REGEL #1: this is the only honest end-to-end proof; capture real output.

## Verification

Full suite green + live E2E output captured.
