---
created: 2026-05-13
status: shipped
priority: high
resolved: 2026-05-13
re-resolved: 2026-05-16
related: .ytstack/backlog/curiosity-dashboard.md, .ytstack/backlog/architecture-deepening.md
---

> **Resolved 2026-05-13:** Option B shipped. `scripts/curiosity/` Sub-Package mirrors `suggestions/`: `producer.py` (extrahiert aus `compile.py`), `cli.py` (Operator-CLI `wiki curiosity`), `backends/email.py` (verarbeitet `email-deep-scan` Requests via existing Mailbox-adapter `scan_deep`). Piggyback `curiosity_followup` (24h cooldown) ruft `--run-oldest` automatisch. Future request types plug in als `backends/<type>.py`. Siehe FEATURES.md Tabelle "Side loops" und PROCESS.md §7.
>
> **Re-resolved 2026-05-16 (false-shipped claim corrected):** Die 2026-05-13-Lösung war strukturell richtig aber operationell unvollständig. Drei zusammenhängende Gaps aufgedeckt nachdem ein lxw-compile-batch 176 pending requests angezeigt hat: (1) `curiosity_followup` Piggyback existierte als engine-default in `config.py`, wurde aber **nie über `KEY_ADDITIONS` in operator configs injiziert** — Vault-Configs hatten den Block einfach gar nicht, also fired der Piggyback nie. (2) Selbst wenn er gefired hätte, war die Cmd `--run-oldest` = 1 request/fire × 24h cooldown = 1/Tag drain — bei typical 3 requests pro compile-source-batch klar unter producer rate. (3) Bei akkumuliertem backlog würde ein `--run-all` thundering-herd-Risiko erzeugen (lange Mailbox-Scans, knock-on 176 neue raw/notes/email/deep-*.md → next compile-cycle). Fix in einem commit: neue cli flag `--run-batch N` (drain N oldest per fire), piggyback nutzt jetzt `--run-batch {max_per_run}` mit default `cooldown_hours=6, max_per_run=5` (= 20/Tag), KEY_ADDITIONS injiziert das in operator configs. Siehe commit-message für details.

# Curiosity-Loop — Konsumenten-Lücke (Producer arbeitet, Executor fehlt)

## Befund

Der Curiosity-Loop ist **producer-only**. `compile.py:maybe_generate_curiosity_requests` läuft nach jedem Compile, ruft Gemma4 via Ollama, erkennt Wissenslücken, schreibt `raw/requests/request-{slug}-{date}.json` mit Schema `{"type": "email-deep-scan", "folder": ..., "topic": ..., "rationale": ...}`.

Der historische Konsument war `scripts/scan-email.py --follow-requests`: las den ältesten pending Request, führte Deep-Scan für den Ordner durch (Bodies lesen, Thread-Rekonstruktion, LLM-Filterung), markierte Request als `done`. Output: `raw/notes/email/deep-*.md` für den nächsten Compile-Zyklus.

**Mit Commit `14bf844` (M002/S02, Email → Collector-Pattern) wurde `scan-email.py` gelöscht.** Der `--follow-requests`-Code-Pfad wurde nicht in `collectors/email_collector.py` mitportiert. Requests akkumulieren in `raw/requests/`, niemand liest sie ab.

## Impact

- **Feature verloren**: Der Curiosity-Loop ist eine zentrale Design-Säule (siehe `docs/concept.md` "Curiosity loop", `docs/architecture.png`). Heute schreibt der Producer Requests die niemand abarbeitet.
- **Disk-Wachstum**: `raw/requests/` läuft langsam voll mit Stale-Requests.
- **Doku-Drift**: README, concept.md, PROCESS.md (vor 2026-05-13 sync) und architecture.png haben das Feature beschrieben als ob es existiert.

## Reaktivierungs-Optionen

### Option A — Deep-Scan-Modus in EmailCollector (empfohlen)

Erweitere `collectors/email_collector.py`:
- Neuer SPEC-Flag `supports_deep_scan: bool = True`
- Neue `run()`-Variante (oder neuer Mode-Param) der Read folder/topic aus dem ältesten Request liest, Bodies aus den Adapters lädt, optional via Ollama filtert, Output in `raw/notes/email/deep-<topic>-<date>.md` schreibt, Request als `done` markiert.
- Adapter-Interface braucht eine `read_bodies(folder, limit)`-Methode — Mailbox-Adapter müssen das nachziehen (Thunderbird-mbox kann's via stdlib `mailbox`, Gmail via API `messages.get(format='full')`, IMAP via `FETCH BODY[]`).

Vorteil: Feature lebt im Collector-Pattern, kein paralleler Code-Pfad.

### Option B — Separater `scripts/curiosity/` Sub-Package

Spiegelt das `suggestions/`-Pattern:
- `scripts/curiosity/producer.py` (extrahiert aus compile.py)
- `scripts/curiosity/cli.py` (interaktiv: list/run/clear pending requests)
- `scripts/curiosity/consumers/email.py` (deep-scan via email-Collector-Adapter)

Vorteil: Symmetrie mit `suggestions/`. Nachteil: zweiter Code-Pfad neben dem Collector-Pattern.

### Option C — Hardcoded Cleanup statt Reaktivierung

Producer abschalten (`features.curiosity_loop = false` default), Requests-Folder leeren, Doku auf "removed" setzen, in DECISIONS.md eintragen.

Vorteil: Realität reflektieren ohne Aufwand. Nachteil: zentrale Design-Säule entfernt.

## Vorgeschlagene Reihenfolge

1. **Sofort**: README + concept.md + architecture.png honestly flag (done in commit `d650340`).
2. **Diese Milestone**: Entscheidung A vs B vs C — empfohlene Default-Wahl A (matches Collector-Pattern).
3. **Implementation**: Adapter-Erweiterung `read_bodies` zuerst (alle drei Adapter), dann Collector deep-scan run, dann Smoke-Test gegen einen real existierenden Request.
4. **Backfill**: Dashboard-Surface (`curiosity-dashboard.md` backlog item) für die Triage.

## Tests

- `tests/test_email_collector_deepscan.py` — fake reader returns 5 mock messages, deep-scan filtert auf topic-relevant, schreibt korrektes Output-File, markiert request als done
- Smoke: `wiki collect email --deep-scan` (oder `--follow-requests`-Re-Branding) gegen einen vorhandenen Request

## Out of scope

- Generische Curiosity-UI über alle Collectors (das ist `curiosity-dashboard.md`)
- Curiosity producer für non-email Sources (jamie könnte zB Meeting-Themen als Gap markieren — separater Vorschlag)

## Provenance

Lücke surfaced beim `/sync-process-docs` + `/concept-update` Pass am 2026-05-13. Hatte sich vermutlich beim M002/S02 Refactor unbemerkt versteckt: PROCESS.md beschrieb das Feature weiterhin, weil niemand den Cross-Reference geprüft hat.
