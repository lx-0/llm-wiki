---
milestone: M024
project: llm-wiki
created: 2026-05-21T19:23:37+02:00
size: M
---

# M024 -- Context

## Goal

The gmeet collector ingests Gemini Meet docs announced via `gemini-notes@google.com`
emails -- colleague-owned, org-shared meetings the own-Drive folder-scan can never
see -- through the existing export/pair/render/dedup pipeline.

## Exit criteria

- `wiki collect gmeet` discovers docs from `gemini-notes@google.com` emails (per
  account, since watermark) and ingests them into `raw/transcripts/gmeet/`,
  deduplicated against folder-scan results by Drive file-id.
- Doc-id extraction is a tested pure function (regex over the `docs.google.com/
  document/d/<id>` URL form), robust at 0 / 1 / N links per mail.
- `export_doc` returns correct UTF-8 (German umlauts intact) -- regression covered.
- New config knob lands in `config.example.yaml` + `templates/` + a
  `migrate_config_keys.py` entry in the same commit; documented in `docs/PROCESS.md`.
- E2E on lxw: a real `gemini-notes@google.com` mail -> ingested file with clean
  content (no mojibake), deduped on re-run.

## Size

M -- see `M024-ROADMAP.md` for slice breakdown.

## Decisions locked in discuss phase

- 2026-05-21: feasibility proven empirically BEFORE planning. Read-only probe with
  alex@yesterday-ai.de's existing `gmail-yesterday` gmeet token (scope
  `drive.meet.readonly`) successfully read metadata + exported the full markdown of
  a doc owned by `chris@yesterday-ai.de` (`shared: True`). Conclusion: the scope is
  per-Meet-origin, not per-owner -- colleague-owned org-shared Gemini docs are
  reachable with the token already in the vault. No new OAuth scope / consent needed.
- 2026-05-21: architecture = `discovery = folder-scan ∪ email-link-scan`. Email
  discovery is a SECOND source of Drive doc-ids; everything downstream
  (`export_doc` -> pair-by-meeting_key -> `_render_markdown`/`_merge_into_sibling`
  -> skip-by-file-id) is reused unchanged. No new output shape, no new dedup key.
- 2026-05-21: the `export_doc` UTF-8 bug was found during the probe (`r.text`
  decodes Google's charset-less `text/markdown` as Latin-1 -> `Ã¤` for `ä`). It
  already corrupts Alex's OWN German meeting notes today, so the fix ships in this
  milestone, not deferred. Fix: decode `r.content` as UTF-8 (or set `r.encoding`).
- 2026-05-21: one-off already done OUTSIDE the milestone -- the triggering meeting
  (Chris's 2026-05-21 Weekly Sync) was ingested via a throwaway driver reusing the
  collector's render path with the UTF-8 fix applied. File:
  `raw/transcripts/gmeet/2026-05-21--weekly-sync-retro-2026-05-21-13-30-cest--6398b694441e.md`
  (101 lines, clean UTF-8). M024 makes this recurring + sanctioned.

## Open questions

- Config shape: a per-account `gmeet.email_discovery` sub-block vs. a top-level
  `gmeet.notes_senders` list. Resolve in S02. Leaning: per-account, since the
  mailbox + token are already per-account; default sender
  `gemini-notes@google.com`, overridable.
- Mailbox read path: reuse `adapters/mailbox/` readers (the `gmail-yesterday`
  account already has `filter.kind: gmail-api`) vs. a narrower direct query.
  Resolve in S01/S02 -- prefer reusing the existing reader so the
  no-GCP-project / thunderbird-mbox accounts also work.
- Watermark: separate email-discovery watermark sub-key vs. reuse the per-account
  `gmeet-state.json` `last_seen_ts`. Folder-scan keys on `createdTime`; email
  discovery would key on mail date or message-id. Resolve in S02.
- Diagram: does this need an infographic touch? gmeet is already a substrate box;
  an email-discovery source may fold into the box caption rather than a new
  element. Decide in S03 against the steady-state-portrait rule.
