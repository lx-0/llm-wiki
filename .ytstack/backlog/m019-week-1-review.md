# M019 wedge — 1-Wochen-Review-Checkpoint (2026-05-24)

**Forcing function:** Operator startete daily-mode am 2026-05-17 mit der
expliziten Absicht, eine Woche zu tweaken und dann zu entscheiden ob/wie
auf weekly umgestellt wird. Diese Datei stellt sicher dass der Checkpoint
nicht vergessen wird.

## Was am 2026-05-24 angeschaut werden muss

1. **7 Runs durch (täglich, plus Pass-1 analyst per run).** Daily-mode
   sollte ~7 Studien-runs + 7 Pass-1 outputs produzieren. Pass-2
   cross-study fired weekly (cooldown 168h) → erster Pass-2 sollte
   am ~2026-05-24 entstanden sein.

2. **Coverage-Trend per Instrument:**
   - WHO-5: erwarte 80% stabil (das einzig single-run-bandable).
   - GAD-7 / PHQ-9 / PSS-10: bleiben partial bis operator
     `wiki study answer` für substrate_inferable:false-items genutzt
     hat. Open: hat operator Q9 (PHQ-9) + andere structurally-null
     items gefüllt? Falls nein → coverage bleibt strukturell <80%.

3. **Change-vis funktioniert (Run 2+):**
   - Radar overlay (current solid + previous dashed) sichtbar?
   - Coverage-sparkline mit 7 Punkten (statt placeholder)?
   - Per-instrument timelines mit 7 Punkten?
   - Δ-Spalte im _summary.md cross-instrument table populated?

4. **Analyst-Befunde über Zeit:**
   - Pass-1 outputs vergleichen — werden die `Open questions for
     curiosity-bridge` aufgegriffen, oder bleiben dieselben Items
     immer null?
   - Pattern-stabilität: Wenn der "sleep-deficit + engagement
     preserved"-Befund aus Run-1 in Runs 2-7 weiter dominiert, ist
     das ein **trait-stable signal**, nicht state-driven.
   - Pass-2 (erster cross-study) — was synthetisiert er bei N=1?
     Wahrscheinlich nichts substantielles bis eine zweite Study
     existiert.

5. **Cost-Realität:**
   - Erwartete cost: 7 runs × ~$0.65 + 1 Pass-2 = ~$4.60 / Woche.
   - Tatsächliche cost aus run-frontmatter `cost_usd` summieren.
   - kind=unknown-Retries: trat das auf? Wie oft? Retry-Pattern
     funktioniert?

## Tweaking-Entscheidungen die hier landen

Operator-Entscheidung am 2026-05-24:

- **Schedule:** daily → weekly umstellen? Oder weiter daily falls
  Befunde noch unklar?
- **Instrumente:** Composition weiter rebalancieren?
- **Operator-Input-Discipline:** Hat operator regelmäßig
  `wiki study answer` genutzt? Wenn nein, ist das ein UX-Problem
  oder Wertproblem?
- **Analyst-Quality:** Pass-1 outputs lesen — sind die Befunde
  operationally useful, oder repetitiv/generisch?

## Files zu reviewen

```
<lxw>/reports/studies/longitudinal-baseline/
├── manifest.yaml                          ← daily schedule, 4 instruments
├── state.yaml                             ← run_count sollte ~7 sein
├── operator_answers.yaml                  ← (falls operator genutzt hat)
├── runs/2026-05-17T14-24-27/              ← run-1 baseline
└── runs/2026-05-24T*/                     ← run-7 (checkpoint)

<lxw>/reports/analyses/
└── 2026-05-2*.md                          ← erste Pass-2 outputs
```

## Ripens

**Hard deadline: 2026-05-24** — eine Woche post-wedge-launch. Operator
explizit auf "nach einer woche dann auch die regebnisse anschauen,
tweaken und dann ggf auf woechentlich umstellen". Nicht ignorierbar.

## Status

**PENDING** — checkpoint scheduled via `/schedule` 7d from 2026-05-17.
