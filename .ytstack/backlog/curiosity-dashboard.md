---
created: 2026-05-03
status: deferred
context: Generische Dashboard-Surface für alle Curiosity-Loop-Requests, kollektiv über Collectors hinweg
related: .ytstack/backlog/collectors.md, .ytstack/backlog/youtube-intake.md, .ytstack/backlog/screenshots-intake.md, .ytstack/backlog/vault-dashboard.md, .ytstack/backlog/obsidian-plugin.md
---

# Curiosity-Loop — Dashboard Surface

Der Curiosity-Loop (collectors.md, "Compile generiert ingest requests for next run") produziert heute Files in `raw/requests/*.json` ohne UI-Surface. Das `Dashboard.md` (M003-S01 shipped) hat Triage-Queues für Compile-Output, aber keine für Curiosity-Requests. Dieses File beschreibt die **generische** Approve/Reject-UI, die für alle Collectors (YouTube, email, screenshots, NAS, …) funktioniert.

## Problem

- Curiosity-Requests sind heute "halbblind": sie werden geschrieben, aber niemand sieht sie außer beim manuellen `ls raw/requests/`.
- `wiki follow-requests` führt sie sequentiell aus, ohne dem User zu zeigen *was* gleich passieren wird (Cost? Welche Quelle? Welche Tier-Eskalation?).
- Es gibt keine Approve-Gate. User kann den Loop nur hart steuern (alle ausführen / gar nicht ausführen / Datei löschen).

## Ziel

Pro Curiosity-Request ein Callout im Dashboard mit:
- Was angefragt wird (topic / video / thread / file)
- Warum (rationale aus Compile)
- Geschätzte Kosten
- Approve / Reject / Dismiss Buttons (Meta Bind)
- Provider-Wahl wo relevant (local vs cloud)

Ein Klick → execution → Status-Update → Callout verschwindet aus pending.

## Generisches Request-Schema

Alle Collectors schreiben in dasselbe Format. Discriminated union via `kind`:

```yaml
# raw/requests/<collector>-<id>.yaml  (yaml statt json — Mensch + Meta-Bind freundlicher)
id: youtube-search-cfg-2026-05-03T14
collector: youtube           # youtube | email | screenshots | nas | ...
kind: search                 # search | upgrade | rescan | deep-scan | ...
created_at: 2026-05-03T14:32:00Z
created_by: compile          # compile | flush | lint | manual
rationale: |
  concept article concepts/diffusion-models.md mentions classifier-free guidance
  but has no source explaining the why
status: pending              # pending | approved | rejected | dismissed | executed | failed
estimated_cost_usd: 0.07     # 0 if local-only or zero-cost
estimated_runtime_s: 180

# kind-spezifische payload
payload:
  topic: "diffusion model classifier-free guidance"
  preferred_channels: [3blue1brown, AI Coffee Break]
  tier_on_pick: 2
  candidates: [...]          # filled in by pre-resolve step (yt-dlp ytsearch10)

# nach approve gefüllt
approved_at: null
approved_action: null        # for multi-choice requests, which option was picked
executed_at: null
exit_status: null
```

Das ersetzt `raw/requests/*.json` graduell. Bestehende JSON-Requests bleiben kompatibel — der Reader checkt beide Extensions.

## Dashboard-Section

Eine neue Section unter "Triage queues" im `Dashboard.md`:

```markdown
## 🔁 Curiosity Loop ({{count}} pending, ~${{estimated_total}})

> [!question]+ 🎥 youtube-search · CFG explanation
> concept article concepts/diffusion-models.md mentions classifier-free guidance but has no source explaining the why
> **Top candidates** (yt-dlp ytsearch10):
> 1. 3blue1brown — Why CFG (14:32, 1.2M views) ★★★
> 2. AI Coffee Break — CFG Explained (8:14, 87k views) ★★
> 3. Yannic Kilcher — CFG paper review (42:11, 230k views) ★
>
> Cost: $0 (search-only) · Pick triggers Tier-2 ingest ($0)
> `BUTTON[curiosity-pick-1]` `BUTTON[curiosity-pick-2]` `BUTTON[curiosity-pick-3]` `BUTTON[curiosity-dismiss]`

> [!warning]+ 🎥 youtube-upgrade · "Attention is all you need explained"
> visual proof at 14:00 not captured in transcript
>
> Cost: $0 local (~3min on kcma) · $0.07 cloud
> `BUTTON[curiosity-approve-local]` `BUTTON[curiosity-approve-cloud]` `BUTTON[curiosity-reject]`

> [!info]+ 📧 email-deep-scan · thread "Q3 architecture review"
> 8 messages, 4 attachments — flagged via metadata stage as high-relevance
>
> Cost: $0.04 (Tier-3 LLM body parse)
> `BUTTON[curiosity-approve]` `BUTTON[curiosity-reject]`

> [!info]+ 📸 screenshots-rescan · screenshot 2026-04-29T1812
> previous run hallucinated project name; user adjusted CONFIG.project_examples
>
> Cost: $0 (local gemma4)
> `BUTTON[curiosity-approve]` `BUTTON[curiosity-reject]`
```

Render via Dataview/Bases-Query auf `raw/requests/*.yaml` mit `status == pending`. Pro request ein Callout, Callout-Type aus `kind` gemappt:
- `search` → `[!question]`
- `upgrade` / `deep-scan` → `[!warning]`
- alles andere → `[!info]`

Icon-Mapping pro Collector: 🎥 youtube, 📧 email, 📸 screenshots, 💾 nas, 🌐 browser, 📰 rss.

## Button-Mechanik

Meta Bind buttons (existierendes Plugin im Dashboard). Generischer Handler:

| Button-ID | Aktion |
|---|---|
| `curiosity-approve` | `wiki curiosity --approve <id>` |
| `curiosity-approve-<provider>` | `wiki curiosity --approve <id> --provider <local\|cloud>` |
| `curiosity-pick-<N>` | `wiki curiosity --approve <id> --pick <N>` |
| `curiosity-reject` | `wiki curiosity --reject <id>` |
| `curiosity-dismiss` | `wiki curiosity --dismiss <id>` (= reject + nie wieder vorschlagen) |

Die Request-ID wird vom Render-Step in den Button-Namen gebakt — Dataview-Template `BUTTON[curiosity-approve-{{request.id}}]`. Meta-Bind-Constraint (Buttons NICHT in `<div>`-Wrappern, Layout via `cssclasses` Frontmatter — bekannte Vault-Constraint) gilt hier wie überall sonst.

## CLI

`scripts/curiosity.py` als zentraler Resolver:

```python
def approve(request_id: str, provider: str | None = None, pick: int | None = None) -> int:
    req = load_request(request_id)
    handler = COLLECTOR_HANDLERS[req["collector"]][req["kind"]]
    exit_code = handler(req, provider=provider, pick=pick)
    update_status(request_id, "executed" if exit_code == 0 else "failed")
    return exit_code

def reject(request_id: str) -> None: ...
def dismiss(request_id: str) -> None: ...

# Pro Collector ein Handler-Modul
COLLECTOR_HANDLERS = {
    "youtube": {
        "search":  youtube_resolve_search,
        "upgrade": youtube_resolve_upgrade,
    },
    "email": {
        "deep-scan": email_resolve_deep_scan,
        "thread-focus": email_resolve_thread_focus,
    },
    "screenshots": {
        "rescan": screenshots_resolve_rescan,
    },
    ...
}
```

Approve läuft asynchron (long jobs blockieren das Dashboard nicht). Status-Update nach Exit:
- success → `status: executed`, Callout verschwindet
- failure → `status: failed`, Callout bleibt mit "❌ Failed" Hinweis und Retry-Button

## Status-Lifecycle

```dot
pending ──approve──▶ approved ──run──▶ executed
   │                                        │
   ├──reject──▶ rejected                    │
   │                                        │
   ├──dismiss──▶ dismissed                  │
   │              (nie wieder vorschlagen)  │
   │                                        │
   └◀───────────── failed ◀──run-fails──────┘
                     │
                     └─retry──▶ approved
```

`dismissed` schreibt einen Marker pro `(collector, kind, payload-hash)` — beim nächsten Compile-Lauf erkennt der Curiosity-Generator, dass dieser Vorschlag bereits abgelehnt wurde, und überspringt ihn. Verhindert "der Loop fragt mich jeden Tag das gleiche".

## Pre-Resolve für Search-Requests

Search-Requests (z.B. youtube-search) brauchen **vor** dem Dashboard-Render einen Pre-Resolve-Step der die Kandidaten füllt — sonst klickt der User in den Wind. Pipeline:

```text
compile.py erzeugt request:
  {kind: search, payload: {topic: ..., preferred_channels: [...]}}
       │
       ▼
hooks/curiosity-pre-resolve.py (after-compile)
       │
       ├─ collector=youtube → yt-dlp ytsearch10:topic
       ├─ collector=email   → IMAP search
       ├─ collector=nas     → find . -name pattern
       └─ ...
       │
       ▼
request bekommt payload.candidates = [...] gefüllt, status bleibt pending
       │
       ▼
Dashboard rendert Callout mit pick-Buttons
```

Pre-Resolve ist günstig (Suche ist meistens frei) und passiert proaktiv, damit der User im Dashboard sofort entscheidungsreife Optionen sieht.

## Filter-Views (Bases)

Drei gespeicherte Bases-Filter:

- **All curiosity (pending)** — Default, alle Collectors gemischt
- **By collector** — Drill-down (nur YouTube / nur Email / …)
- **High-cost only** — `estimated_cost_usd > 0.10` (für gezielte Cost-Triage)

## Mobile

Meta-Bind buttons rendern auf Obsidian Mobile, aber `child_process` nicht (kein lokaler Python-Runner). Mobile-Verhalten:

- Pending-Callouts werden read-only gerendert mit 🖥️-Icon vor den Buttons
- "Mobile queue" Section zeigt Requests, die der User auf dem Handy markiert hat (`status: mobile-approved`)
- Beim nächsten Desktop-Open / Cron-Hook auf kcma laufen die mobile-approved Requests automatisch

Alternative für Mobile: REST-Endpoint auf kcma-d8 (z.B. FastAPI) der `wiki curiosity --approve` HTTP-getriggert ausführt. Defer — erst wenn Mobile-Use real wird.

## Cross-Surface — Plugin-Sidebar

Symmetrisch zu obsidian-plugin.md: das geplante Plugin im *primary* Vault zeigt dieselben Requests in der Sidebar. Beide UIs lesen `raw/requests/*.yaml`, beide rufen `wiki curiosity --approve` auf. Single source of truth, doppelte Surface (Wiki-Vault Dashboard für tiefe Sessions, Primary-Vault Sidebar für leichte Triage).

## Implementation-Phases

1. **Schema-Migration** (~2h) — `raw/requests/*.json` → `*.yaml`, `kind`-Feld, `status`-Lifecycle, Reader liest beide Formate während Übergang.
2. **`scripts/curiosity.py` CLI** (~3h) — `approve` / `reject` / `dismiss` / `list`. Handler-Registry pro Collector. Async-Run + Status-Write-Back.
3. **Pre-Resolve-Hook** (~2h) — `after-compile` hook ruft pro neuem search-Request den Collector-Resolver auf. yt-dlp ytsearch / IMAP / fs-find.
4. **Dashboard-Section** (~2h) — Dataview/Bases-Query, Callout-Rendering, Meta-Bind-Buttons mit dynamischen IDs.
5. **Dismiss-Memory** (~1h) — `(collector, kind, payload-hash)` Marker, Compile-Curiosity-Generator respektiert.
6. **Bases-Filter-Views** (~30min) — gespeicherte Filter ins `templates/.obsidian/`.
7. **Mobile-Read-Only** (~30min) — `cssclasses: mobile-readonly` wenn `Platform.isMobile`, CSS disabled buttons.

Reihenfolge: 1+2 sind Voraussetzung für alles. 3+4 zusammen ergeben den ersten sichtbaren Win. 5-7 inkrementell.

## Open Questions

- **YAML vs JSON für Requests:** YAML ist Mensch- und Frontmatter-freundlicher (Meta Bind kann Frontmatter direkt lesen), JSON ist Maschinen-strikter. Recommendation: YAML mit JSON-Schema-Validierung.
- **Granularität von dismiss:** Per-request oder per-pattern? "diesen einen Vorschlag" vs "nie wieder Channel X". Recommendation: per-request default, per-pattern via separater Skill / Config.
- **Concurrent approves:** wenn User 5 Buttons schnell hintereinander klickt — queue oder parallel? Recommendation: queue (max 1 LLM-Job zur Zeit, sonst Rate-Limits + Cost-Spikes).
- **Failure-Notification:** `notify-send` (Linux/macOS) oder Obsidian Notice (geht nur wenn Obsidian läuft)? Recommendation: beides — append failure ins `raw/requests/.failures.log`, plus Notice wenn Obsidian-Plugin aktiv ist.
- **Cost-Confirmation für teure Requests:** ab welcher Schwelle nochmal nachfragen? `estimated_cost_usd > 0.20` → Modal "really?". Recommendation: ja, simple threshold in CONFIG.

## Reihenfolge / Priorität

Voraussetzung: mindestens **ein** Collector hat tatsächlich Curiosity-Requests im Einsatz. Heute: email-collector hat den Mechanismus, screenshots evtl. Wenn YouTube (youtube-intake.md) als zweiter Collector mit Curiosity-Loop landet, lohnt sich diese Surface.

Vorher: minimaler Pfad reicht (`wiki follow-requests` blind ausführen). Diese Surface ist eine Quality-of-Life-Investition wenn der Loop ≥ 5 Requests/Woche produziert.
