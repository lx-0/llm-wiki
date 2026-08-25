# lxw Vault Audit — 2026-08-25 (full-state, read-only)

Six parallel axes over the live vault: structural health (engine tools), token/feature
usage, substrate freshness, corpus quality, log mining, config-vs-reality. Engine at
`f281555`+, vault 2025 knowledge articles. Method: doctor/links/dedup/menu/usage JSON
seams + filesystem/state/log reads; NO writes, no LLM-costing commands.

## Kernbild

Die Server-/API-Seite der Pipeline ist gesund und aktuell (email, calendar, health,
jamie, compile, studies, publish). **Aber zwei Cluster sind seit Wochen tot und ein
dritter degradiert — das sind 3 gemeinsame Ursachen, nicht 15 Einzeldefekte:**

1. **Flush-Extraktion tot seit ~2026-08-14** (~99% Failure): bundled CLI stirbt still
   (exit 1, leerer stderr, 4–6 s) bei Inputs von 57–87 KB — die bekannte fragile
   Size-Class; `flush_extract` pinnt kein Modell ("(default)"). 165× "failed after 3
   attempts" in 30 d; **Retry-Queue divergiert: 234 archivierte Kontexte (~17 MB)**,
   Drain nur 5/Compile-Tag bei 2 Compile-Tagen/30 d. Folge: `daily/<d>/sessions.md`
   zuletzt 2026-08-05 — das Session-Substrat (Kern von Path A) fehlt seit 20 Tagen.
2. **Ollama-Cluster tot seit ~2026-06-22** (kcma-d8 offline): curiosity (Queue: 904
   Requests, 709 pending, eingefroren), review-wiki (failed), vision/classify (letzte
   gemma4-Calls 06-13). 0 Ollama-Tokens seit 06-22.
3. **Geräteseitiger Intake + Queue-Konsum stehen seit Mitte Juni**: screenshots
   (64 d), pictures (75 d), voice (73 d), inbox-mobile-Bridge (72 d), Triage (65
   pending, alle detected 06-14/15), Suggestions (10 pending, älteste 130 d). Muster
   spricht für gemeinsame Mac-seitige Ursache (Bridge-LaunchAgent/iOS-Shortcuts),
   nicht Einzeldefekte.

Dazu: **Compile lief in 30 Tagen an genau 2 Tagen** — alle Piggybacks (dream, digest,
retry, lint) hängen an dieser Kadenz. Dream dadurch faktisch stehend: 110 Entities
overdue, die AKTIVSTEN (sidney-wach, chris-von-rhein — je 16–18 Index-Duplikate) 86 d
unsynthetisiert; `updated` bleibt frisch (Ingestion läuft), die SYNTHESE fehlt.

## Fehler (Engine — im Repo fixbar)

- E1 **Lint-Check-Crash**: `'Concept domain tag' crashed: '<' not supported between
  instances of 'str' and 'int'` — ein Check läuft gar nicht (lint-2026-08-24.md:333).
- E2 **Bash-`[[ … ]]` als Wikilink geparst**: `[[ -f "$logfile" ]]` etc. in live-Zeilen
  (außerhalb Fences) → False-Positive-Klasse in lint/links UND **publish degradiert
  solche Stellen zu Klartext** (Render-Pass) — Inhaltskorruption-Klasse im Mirror.
- E3 **`models.compile_model` ist toter Knob**: route.py hardcodet
  `claude-haiku-4-5-20251001` in allen Routen; `claude-opus-4-8` (plain) hat 0 Calls
  all-time. Knob lügt — entfernen/umbenennen oder Route auf CONFIG stellen (Decision).
- E4 **9 Engine-Keys fehlen im Vault-Config** (piggybacks.daily_digest_yesterday/*,
  piggybacks.health/*, 4 limits-Keys, graph_view.domain_tags) — laufen auf
  Dataclass-Fallback, exakt das Versteckspiel, das die CLAUDE.md-Hard-Rule verbietet.
- E5 **piggyback_runner überschreibt `last_error` nicht** auf dem rc≠0-Pfad —
  review-wiki zeigt stale "killed after 14400s" vom Vortag (echter Lauf: 8.5 s, rc=1).
- E6 **operations.md hat zwei Writer**: Compile prependet mit kaputtem Timestamp
  (`2026-08-24T[compilation]:`), Dream appendet — Tail ≠ neueste Einträge.
- E7 **gmeet Drive-Export-404 ohne Dead-Letter**: ID `1Qx7dq…YbP0` scheitert bei jedem
  Lauf erneut (Backlog `gmeet-export-dead-letter.md` existiert bereits — Hot machen).
- E8 **Legacy-Dollar-Zähler läuft weiter** (`total_cost=305.89`, +3.66 am 08-24) —
  Widerspruch zu DECISIONS 2026-05-23 (Token-only).
- E9 **Dedup-Anzeige**: "fuzzy title 1.00" für erkennbar verschiedene Titel —
  Score-/Display-Bug oder Shared-Source-Boost verdeckt echten Wert.
- E10 `piggybacks.scan_youtube` totes Config (kein Task dahinter); `capture` spawnt
  nie (capture_inbox leer — konsistent, aber im State irreführend "konfiguriert").

## Fehler (Vault-Content)

- V1 **index.md massiv gedriftet**: 1844 Rows, nur 1482 unique vs 2022 real — **561
  Artikel fehlen**, **362 Duplikat-Rows** (sidney-wach 18×), 42 dangling Junk-Targets
  (`[[! -o monitor]]`, `[[foo]]`). Folgeschaden: publish-Descriptions für 561 Artikel
  laufen auf Absatz-Fallback statt Index-Summary.
- V2 **321 broken links / 199 dangling refs** (21 auto-fixable via `links --fix`),
  333 Orphans, 294 sparse (271 davon `imported-*`/Listen-Artefakte).
- V3 **513 Hard-Fact-Negation-Warnings, davon 377 = Fleet/Township-Rename** — ein
  gezielter Sweep (`wiki correct apply` / reconcile) tilgt ~34% aller Warnings. Der
  betroffene Fact hat als einziger **kein trust/sources-Feld**.
- V4 5 Near-Empty-Junk-Artikel (`imported-links`, `leadsammler`, …); 5/9 Facts
  `applied: false` (2 davon trust: confirmed); Domain-MOCs seit 2026-05-15 eingefroren
  (~300 neue Artikel seither); `projects/demos.md` hält allein 10 fehlende Embeds.

## Usage-Analyse (Features nach realer Nutzung)

- **Träger**: compile (Haiku-Routen, 83% des All-time-Inputs; 12.7M in am 08-24),
  intents (Haiku, aktiv), studies/analyst (laufen, ISI auf Sonnet gepinnt), publish
  (frisch, Piggyback seit 08-25), email/calendar/health/jamie-Collector.
- **Ungenutzt/tot**: `wiki query` 33 d ohne Call (119 all-time; qa/ = 1 Datei) ·
  Ollama-Features komplett (s. o.) · youtube (configured=false, Altdaten) ·
  browser/tabs (1 Datei, 99 d) · folder-index (76 d stale) · voice/pictures/
  screenshots (Intake tot) · optimize_claude_md (1 Crash 06-11, seither aus, nie
  root-caused).
- **Aus, obwohl Substrat perfekt da**: `health_trends` (Oura täglich aktuell,
  2014–2018 backfilled, Knobs getuned!) · `concept_reconciliation` (5 Facts + der
  377-Warning-Fleet-Case ist exakt sein Job) · `clippings_sweep: true` ist No-Op
  (Quelle `Clippings/` existiert nicht).
- Kurios: `claude-sonnet-4-6` und einst `qwen2.5vl:7b` im Ledger ohne Config-Quelle
  (Sonnet = ISI-Instrument-Pin; ok).

## Learn & Improve (abgeleitet)

Sofort-Fix-Kandidaten (Engine, S-Klasse, je mit Test): E1 Lint-Crash, E2
Bash-Bracket-Linkklasse (lint+links+publish gemeinsam), E5 stale last_error, E4
Migration-Nachtrag, E8 Dollar-Zähler-Stilllegung, E7 gmeet-Dead-Letter.
Root-Cause-Arbeit (eigener Block, systematic-debugging): **Flush-cli_crash-Klasse**
(57–87 KB, kein Modell-Pin — Memory: "Same SDK exit-1-empty-stderr → 3 distinct root
causes") + Retry-Drain-Mechanik (5/24 h reicht nie). **Index-Drift-Klasse** (Dedup der
Rows + Nachtrag der 561 — vermutlich Compile-Writer-Bug bei Duplikat-Erkennung).
Operator-Entscheide: kcma-d8 wieder online (entsperrt 3 Features) · Mobile-Bridge/
LaunchAgents prüfen (entsperrt 4 Intake-Kanäle) · health_trends + reconciliation
einschalten? · Fleet/Township-Sweep fahren · Triage-65/Suggestions-10 abarbeiten oder
verwerfen · Compile-Kadenz (2 Tage/30 macht alle Piggybacks zur Theorie — Scheduler-
Backlog `system-level-scheduler.md` adressiert genau das).

Neue Backlog-Einträge aus diesem Audit: `flush-extract-outage.md`,
`index-md-drift.md`, `bash-brackets-wikilink-class.md`. KNOWLEDGE-Eintrag: Audit-Lehre
(Server-seitig überlebt alles, geräteseitig + Queue-Konsum sterben lautlos im Cluster
— Full-State-Audit gehört auf Kadenz, nicht auf Zuruf).
