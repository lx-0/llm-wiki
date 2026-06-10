# Curiosity request dedup — per-folder supersede

**Status:** proposed (operator undecided, 2026-06-10)
**Origin:** 2026-06-10 deep-scan root-cause session (commit `3cedfc4`, CHANGELOG 0.1.8)

## Problem

After the folder-resolution fix + `cleanup_empty_deep_scans.py --apply`, the
reference vault has **763 pending** email-deep-scan requests that drain via the
`curiosity_followup` flush-piggyback at 5 per ≥6h (~20/day → ~5 weeks).

The scan result depends only on `(account, folder)` — `topic` is report framing,
not a search filter (`scan_deep` pulls the newest ≤50 bodies of the folder).
The 763 requests cover only **13 distinct folders** (219× `INBOX/COMPANY/01
Mentoring`, 195× `INBOX/Server`, 97× `INBOX/Vertraege`, …), so the drain
produces hundreds of near-identical reports that the compile pass each distills
individually (Claude SDK cost) for no added knowledge coverage.

## Proposed wedge

Either a `--dedup-per-folder` flag on `cleanup_empty_deep_scans.py` or a small
standalone migration:

- Group pending requests by `(account, folder)`.
- Keep the **newest** request `pending`; flip the rest to `status: "superseded"`
  (new terminal status; `list_pending` already skips anything not pending —
  verify it treats unknown statuses as non-pending, currently it excludes only
  `done`/`rejected`, so `superseded` must be added there OR reuse `rejected`
  with a `superseded_by` breadcrumb).
- Idempotent, `--apply` gated, preview default — same shape as the cleanup
  migration.

→ 13 scans instead of 763, same folder coverage, drain completes in <1 week.

## Alternatives considered

- **Let it drain (current state):** works, just slow + redundant compile spend.
  This is what happens if nothing is built.
- **Dedup by `(folder, topic)`:** keeps more framing diversity for compile, but
  topic does not change the scanned bodies — marginal value over per-folder.

## Open questions

- Producer side: should the producer itself dedupe at request-creation time
  (skip writing a request when a pending one for the same folder exists)? That
  prevents re-accumulation — the 763 grew because requests were re-generated
  daily while results stayed empty. Worth doing in the same arc.
