# Operator financial/operational fact layer — intake gap

**Status:** idea · **Logged:** 2026-06-06 · **Size:** M (mostly intake + PII policy, not engine)

## Origin

Surfaced while filling out a Sparkasse **Selbstauskunft** for the operator
(credit-line for the Wach & Wegener UG) in the `self-orga` project. The task
needed hard personal-finance facts: current net salary, KV contribution, rent,
IBAN, securities-depot value, statutory pension, grant income, UG master data.

**Key signal:** the wiki (`lxw`) was queried first and contributed **almost
nothing to the actual numbers**. It confirmed soft context (business email,
phone, UG 50/50 structure, the "KK-Linie Sparkasse" cash-bridge intent via
`concepts/yesterday-corporate-structure` + `concepts/yesterday-team-resource-
utilization-2026-q2`) but **not a single load-bearing figure**. Every decisive
value came from raw sources the wiki does not ingest.

## Problem

The vault has a rich *narrative/relational* layer (people, projects, decisions)
but no **financial/operational fact layer**. When an agent needs "what is the
operator's current income / fixed costs / assets / company master data", the
wiki can't answer — it has to re-derive from scattered raw documents every time.
That re-derivation is exactly what just happened (3 parallel extraction agents
over `Private/Documents`, `Work/Company`, postal-inbox photos + a depot CSV).

## What had high impact (ranked) — candidate substrate

1. **Bank statements** (`Private/Documents/30 Finanzen/.../Volksbank .../Konto-
   auszuege`) — net salary, recurring debits (KV, rent, insurance), IBAN.
   Highest signal density of any source. → derived facts worth caching;
   **raw = PII, do not ingest**.
2. **`Work/Company/coaching/business-plan`** — the Gründungscoaching plan
   (Unternehmerlohn private-budget table, market analysis, UG economics).
   **Strongest clean intake candidate**: structured, reusable, low-sensitivity,
   links to `concepts/yesterday-corporate-structure`. Recommend ingest.
3. **Securities depot export** (CSV) — total ~94k, allocation. Derived fact
   useful; raw CSV = PII.
4. **Grant decision** (Gründungsstipendium.NRW, Projektträger Jülich) — 1.200
   €/mo, 15.07.2026–14.07.2027, FKZ 005-2602-0022. Clean hard fact, low
   sensitivity. Good intake.
5. **DRV Renteninformation** — Entgeltpunkte → pension anwartschaft. Derivable.

## Proposed (decide later, operator-gated)

- A **`facts/`-style financial/company sub-domain** (or dedicated entity pages:
  `wach-wegener-ug` master data, an operator-finance fact node) holding *derived*
  hard facts with as-of dates — NOT raw statements.
- **PII policy first**: most high-impact sources are sensitive. Need an explicit
  rule for what becomes a wiki fact vs. stays out (bank/depot/Ausweis/tax-ID =
  out; grant terms, UG register data, budget structure = candidate in). This
  policy is the actual blocker, not the mechanics.
- Possible collector angle: the operator's filing system
  (`~/Sync/.../Private/Documents`, numbered categories) is already structured —
  a future collector could surface *metadata/structure* (which categories,
  recency) without ingesting contents.

## Caveats

- Sensitivity is the gating concern — this is why it's an idea, not a hot ticket.
- Cross-refs: self-orga `Sparkasse-Selbstauskunft.md` (the worked example) and
  `Curiosity-Requests.md` (#2/#4–14) document the exact fields + sources.
- Don't over-build: the value is "agent can answer operator-finance questions
  without a 3-agent raw-document sweep", not a full PFM system.
