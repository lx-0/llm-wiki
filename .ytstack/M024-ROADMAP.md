---
milestone: M024
project: llm-wiki
size: M
created: 2026-05-21T19:23:37+02:00
status: done
total_slices: 3
completed_slices: 3
---

# M024 Roadmap

**Goal:** The gmeet collector ingests Gemini Meet docs announced via
`gemini-notes@google.com` emails -- colleague-owned, org-shared meetings the
own-Drive folder-scan can never see -- through the existing
export/pair/render/dedup pipeline.

**Exit criteria:**
- `wiki collect gmeet` discovers docs from `gemini-notes@google.com` emails (per
  account, since watermark) and ingests them into `raw/transcripts/gmeet/`,
  deduplicated against folder-scan results by Drive file-id.
- Doc-id extraction is a tested pure function (regex over the doc-URL form),
  robust at 0 / 1 / N links per mail.
- `export_doc` returns correct UTF-8 (umlauts intact) -- regression covered.
- New config knob in `config.example.yaml` + `templates/` + `migrate_config_keys.py`
  in the same commit; documented in `docs/PROCESS.md`.
- E2E on lxw: a real `gemini-notes@google.com` mail -> ingested file, clean
  content, deduped on re-run.

## Slices

Slice detail lives in per-slice `M024-S##-PLAN.md` files, created by
`ytstack:slice-milestone`.

- [x] S01 — UTF-8 export fix + doc-id extraction + reader HTML body (pure, tested) — commit f35cce0
- [x] S02 — email discovery wired into the run loop + config knob + migration — commit f294e51
- [x] S03 — docs (PROCESS + setup-gmeet) + lxw E2E (infographic deferred to backlog) — commit e313eab

## Run order

Slices execute sequentially. After each slice, `ytstack:reassess-roadmap` checks
if the plan still fits reality.

## How to update this file

- Flip slice checkbox `[ ]` → `[x]` when its tasks are all `summarize-task`-confirmed
- Update `completed_slices` count
- On milestone completion, flip `status: planned` → `status: done` and update global ROADMAP.md
