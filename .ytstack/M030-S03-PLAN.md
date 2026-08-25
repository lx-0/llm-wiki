---
milestone: M030
slice: S03
project: llm-wiki
created: 2026-08-25T07:01:45Z
status: done
task_count: 6
completed_tasks: 6
---

# M030-S03 -- Slice Plan

**Goal:** Publishing keeps itself fresh after compile, the feature is documented and visualized, and the reach-anywhere claim is proven end-to-end from another machine with the Mac asleep.

## Tasks

- [x] T01 -- Compile piggyback: `wiki publish` rides the piggyback table (`core/piggybacks.py`, cooldown-gated, detached spawn) after successful compile — as a proper `piggybacks.publish` entry (built-in task table + `_default_piggybacks` in config_schema.py:1035 + migration), NOT a second `publish.piggyback` bool (would recreate the dead-knob drift cleaned up in C13); additionally hard-gated on `publish.enabled`; tests for the gate logic.
- [x] T02 -- Live retraction/restore E2E on dev: delete one article locally → publish archives it upstream (visible as archived in the wiki detail); restore the file → publish restores; a further unchanged rerun performs zero writes. Evidence captured.
- [x] T03 -- Reach-anywhere live proof — CLOSED passed-with-caveats 2026-08-25 (operator: "kann ich leider nicht testen"). Proven: an MCP client answered a personal-context question purely from server-served content (`get_object 95-percent-confidence-rule` → full article with server-side version metadata/sha256; frontmatter verbatim, links as navigable global slugs, backlinks footer). Server-side serving is Mac-independent by construction (K8s + Postgres/S3). CAVEAT — untested: a client on a DIFFERENT machine and the claude.ai custom-connector path; structurally covered (public TLS endpoint, OAuth flow exercised), to be confirmed opportunistically when the operator next works from another device.
- [x] T04 -- Docs: `docs/PROCESS.md` sync (publish stage), `docs/config.md` regen via `config_docs.py --write`, operator setup runbook section (token mint pointer, enabling publish; MUST name the iCloud exposure of `<vault>/.claude/.env` — the vault syncs to Apple's cloud — and offer the Keychain indirection à la `security find-generic-password` as alternative), README touch only if the public feature list changes.
- [x] T05 -- Infographics: fold publish into `docs/architecture.excalidraw` + `docs/overview.excalidraw` as steady-state structure (no SHIPPED/milestone badges), re-render PNGs through the three mandatory gates (bbox-overlap scan, glyph-width scan, zoom-crop review).
- [x] T06 -- Closeout: CHANGELOG + version bump per repo convention (0.4.0 + uv.lock), flip M030-ROADMAP status, `ytstack:reassess-roadmap` at the milestone boundary. (Roadmap flip + reassess happen with T03.)

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`.

## Notes

(Add observations during slice execution. Issues that surface become entries in `DECISIONS.md` or `KNOWLEDGE.md`.)
