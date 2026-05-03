---
created: 2026-05-03
status: deferred
context: Ingest-Erweiterung für YouTube-Lerninhalte; orthogonal zu screenshots-intake / collectors.md
related: scripts/scan-screenshots.py, .ytstack/backlog/collectors.md, .ytstack/backlog/obsidian-plugin.md
---

# YouTube Intake — Multi-Tier Video Ingest

YouTube-Videos sind eine der wichtigsten Lernquellen für den User. Ziel: ein Collector der mehrere Input-Pfade akzeptiert und mehrere Detailgrade pro Video erlaubt. Folgt dem gleichen **Tier-Pattern** wie screenshots-intake (cheap default, expensive on demand) und dem **Curiosity-Loop-Pattern** aus collectors.md (Compile generiert Upgrade-Requests).

## Input-Pfade

Drei Quellen, gleicher Output-Schreibpfad (`raw/notes/youtube/<slug>.md` + `<slug>.json` Sidecar):

| Pfad | Format | Beispiel | Trigger |
|---|---|---|---|
| **A. Inbox-Liste** | unformatierter Markdown — eine URL pro Zeile, optional mit Notiz danach | `raw/inbox/youtube.md` | manuell, oder cron-watcher |
| **B. Obsidian Web Clipper** | community-template "youtube-with-transcript-clipper" schreibt direkt nach `raw/notes/youtube/` | aus Browser, ein Klick | per-Klick im Browser |
| **C. Plugin-Command** (ergänzt obsidian-plugin.md) | Modal mit URL-Eingabe + Tier-Picker | `Wiki: Ingest YouTube URL` | Command-Palette |

Inbox-Parser MUSS robust sein gegen:
- Bare URLs (`https://youtube.com/watch?v=...`)
- youtu.be Shortlinks
- Mobile-Format (`m.youtube.com`)
- URL mit `&t=...` Timestamp (Notes auf bestimmte Stelle)
- Markdown-Links `[Title](url)`
- Begleittext nach URL ("- spannend ab Minute 12")

Begleittext landet im Sidecar als `user_note` und wird im LLM-Prompt mitgegeben → Hinweis worauf zu achten.

## Detail-Tiers

Jeder Tier ist additiv — Tier N enthält alles aus Tier N-1.

### Tier 0 — Metadata-only (≈0 Kosten)

`yt-dlp --skip-download --write-info-json` liefert: `title`, `uploader`, `channel_id`, `duration`, `view_count`, `like_count`, `description`, `tags`, `categories`, `chapters[]`, `upload_date`, `thumbnail`. Keine LLM-Calls.

**Output:** Sidecar mit Metadata, Markdown-Stub mit Embed + Beschreibung. Reicht für "ich hab das gesehen, gehört in Folder X".

### Tier 1 — + Auto-Subtitles (≈0 Kosten)

`youtube-transcript-api` (jdepoix, Python, kein API-Key) ODER `yt-dlp --write-auto-subs --sub-lang en,de`. Subtitles als plain text + Timestamp-JSON.

**Caveat aus Recherche:** Library bricht historisch wenn YouTube interne APIs ändert. Defensive: Fallback auf yt-dlp wenn Library failed. Rate-Limit-Beobachtung: Nutzer berichten Issues nach 100-500 req/h → exponential backoff.

**Compile-Input:** Subtitles werden zum Subject des `compile.py` Prompts (gleicher Pfad wie Article-Compile, aber Source-Type=`youtube-transcript`).

### Tier 2 — + Top-Kommentare (≈0 Kosten)

`yt-dlp --get-comments --extractor-args "youtube:max_comments=100,all,100"`. Top-Level + Replies. Liefert: `text`, `author`, `like_count`, `reply_count`, `is_creator_response`, `parent_id`, `published_date`.

**Wert für Lernkontent:** Kommentare enthalten oft Korrekturen, weiterführende Resourcen, Praxis-Erfahrungen, "Update: das Tool heisst inzwischen X". Filtern auf `like_count >= median * 2` ODER `is_creator_response == True` reduziert Noise.

**Compile-Hinweis:** Kommentare separat im Prompt (`# Community-Kommentare`-Section), nicht mit Transcript verschmolzen — andere epistemische Verlässlichkeit.

### Tier 3-local — Frame-Sampling + gemma4:e4b auf kcma-d8 (≈0 Kosten, langsam)

**Idee:** kcma-d8 (Home-GPU via Ollama, `192.168.2.42:11434`) ist 100% online und kostenfrei. gemma4:e4b läuft dort bereits für screenshots-intake. Statt Gemini-Cloud: yt-dlp lädt Video → ffmpeg sampled Keyframes → jeder Frame durch gemma4 vision → aggregierte JSON-Struktur ähnlich Tier-3-cloud.

**Frame-Sampling-Strategien:**
1. **Chapter-aligned:** Pro Chapter aus Tier-0 ein Frame in der Mitte (`(start+end)/2`). Sparse, schnell. Gut für Lecture/Talk-Format.
2. **Scene-change:** ffmpeg `-vf "select='gt(scene,0.4)'"` extrahiert Scene-Cuts. Gut für Slide-Decks (jeder Slide = neuer Frame), Tutorials mit IDE-Wechseln, Whiteboard-Wisches.
3. **Fixed interval:** 1 Frame / 30s. Worst-case-Default wenn 1+2 nichts geben (Music, Vlog).

Default: Strategy 1 wenn `chapters[]` ≥ 3, sonst Strategy 2, sonst 3.

**Pipeline:**
```python
def gemma_video_ingest(url, meta, strategy="chapter"):
    video_path = ytdlp_download(url, format="worst")  # 360p reicht für vision
    frames = extract_frames(video_path, strategy)     # ffmpeg → list[(ts, png_path)]
    per_frame = [
        ollama_vision(gemma4, prompt_frame, png)
        for ts, png in frames
    ]
    aggregate = ollama_chat(gemma4, prompt_aggregate,
                            transcript=meta.transcript,
                            frame_summaries=per_frame)
    cleanup(video_path, frames)
    return {"model": "gemma4:e4b@kcma", "frames_analyzed": len(frames),
            "per_frame": per_frame, "aggregate": aggregate}
```

**Wo es Gemini ebenbürtig ist** (Großteil des User-Lernkontents):
- Lecture / Conference-Talk (Talking-Head + Slides) — Slides sind Scene-Changes, gemma4 OCR'd den Slide-Inhalt
- Code-Walkthrough / IDE-Tutorial — Scene-Change-Detection greift bei jedem File-Switch, gemma4 liest Code on screen
- Whiteboard-Erklärung — Scene-Change bei jedem Wisch, gemma4 beschreibt das Zeichen
- 3blue1brown-Style Animation — Chapter-aligned Frames sampeln die Key-Visualizations

**Wo es schwach ist** (akzeptabel — diese Inhalte sind eh nicht primary learning):
- Action / Sport / Music-Performance — Frame-Sampling verliert Temporal-Coherence, Gemini's native Video-Tokens sind besser
- Subtitle-loose Demo-Content (Cooking, Crafts) wo das Visual flowt statt cuttet
- Sehr lange Videos (>2h) wo Per-Frame-Aggregation den Kontext sprengt → chunk per chapter

**Caveats:**
- yt-dlp Download nimmt Disk-Space — `format=worst` (~200MB/h Video) + cleanup nach Run.
- gemma4-Throughput auf kcma-d8: ~5s/Frame bei e4b (schätze aus screenshots-intake-Daten). 1h Video × Strategy 2 ≈ 30 Scene-Cuts × 5s = 2.5min — passt easy.
- OCR-Qualität für Code: gemma4 vision kann small text, aber für hochwertigen Code-Capture lohnt sich tesseract als zusätzlicher Layer (sub-second, deterministisch).
- Zwei Inferences nötig: per-frame + aggregate. Aggregate-Prompt muss mit Transcript + Frame-Summaries als Kontext. Bei 30 Frames × ~200 Tokens/Frame-Summary + Transcript = ~10-20k Tokens — gemma4 context-window prüfen.

**Aufwand:** ~4-5h. Schwerster Teil: ffmpeg-Frame-Extraction tunen + Per-Frame-Prompt iterieren.

**Provider-Routing (Default-Verhalten):**

```text
Tier 3 angefragt
   ↓
Ollama (kcma-d8) erreichbar?  ──yes──▶  Tier 3-local (gemma4:e4b)
   │
   no / explicit --provider=cloud
   ↓
Gemini API key vorhanden?  ──yes──▶  Tier 3-cloud (gemini-2.5-flash-lite)
   │
   no
   ↓
Abort mit klarer Fehlermeldung ("set OLLAMA_URL or GEMINI_API_KEY")
```

Local-first ist Default weil 0 Kosten + 100% online (User-Setup). Cloud ist Fallback. Keine stille Eskalation auf Cloud — wenn Ollama mal aus ist und der Run rechnet plötzlich Geld weg, fühlt sich der User verarscht. Daher: auto-fallback nur mit `--allow-cloud-fallback` oder `youtube.allow_cloud_fallback: true` in CONFIG.

**CLI-Override:** `--provider local` / `--provider cloud` zwingt eine Seite. Default = auto-detect (probe `OLLAMA_URL/api/tags` mit 1s timeout).

Beide Provider schreiben in dieselbe `analysis`-Sidecar-Section, das `model:` Feld unterscheidet (`gemma4:e4b@kcma` vs `gemini-2.5-flash-lite`). Compile-Pipeline ist agnostisch — die epistemische Verlässlichkeit beider Outputs ist nahe genug für gleichen Treatment.

### Tier 3-cloud — Full Visual via Gemini 2.5 (≈2-7¢ pro 10min Video)

Gemini 2.5 unterstützt **direkte YouTube-URL-Ingestion** (Preview-Status, aktuell kostenlos für YouTube-URLs als Input — separat von Token-Pricing). Falls Preview endet: Fallback auf File-Upload via Files API (bis 2GB, längere Videos dann downsamplen).

**Modelle / Kosten:**
- `gemini-2.5-flash-lite` — ~2¢ pro 10min Video. Default für Tier 3.
- `gemini-2.5-flash` — ~7¢ pro 10min. Wenn flash-lite zu schwach für visuell dichten Content (Code-Walkthroughs, Whiteboard-Talks).
- `gemini-2.5-pro` — $1.25/1M input ≤200k context, $10/1M output. Nur für Tier-4-Deep-Dive.

**Was Tier 3 hinzufügt** über Subtitles+Kommentare hinaus:
- Visuelle Slides / Whiteboards / Code-on-Screen die nie gesprochen werden
- Korrekturen zwischen Audio und Visualem ("er sagt X, zeigt aber Y")
- UI-Demos (Plugin-Walkthroughs, IDE-Tutorials) wo das Visual = der Content ist
- Diagramme / Architekturen die transcript-only komplett verloren gehen

**Prompt-Strategie:** Strukturiertes Schema → `key_concepts[]`, `visual_artifacts[]` (slides, code, diagrams), `code_snippets[]`, `corrections_to_audio[]`, `chapter_summaries[]`. Pro Chapter ein Eintrag wenn `chapters[]` aus Tier-0 vorhanden — sonst auto-segmenting durch Gemini.

### Tier 4 — Chapter-level Deep Dive

Pro Chapter eine separate Gemini-Inference mit fokussierten Fragen. Triggert sich nur auf User-Markierung (`upgrade: chapter <N>` im Sidecar) oder Curiosity-Request aus Compile (s.u.). Nur sinnvoll bei "diese 3 Min sind das Kerninsight, der Rest ist Intro/Outro".

## Tier-Selection

Pro Video-Ingest wird ein Tier gewählt. Drei Wege, in dieser Priorität:

1. **Explicit im Begleittext:** `tier: 3` oder `tier: 0-only` neben der URL → respect.
2. **Per-Channel-Default in CONFIG:** `youtube.channel_defaults: {"3blue1brown": 3, "Fireship": 1}` — kanonisch wichtige Quellen automatisch deeper.
3. **Heuristic Fallback:** Tier 1 (subtitles) als safe default.

Tier 0 macht nur Sinn wenn Subtitles disabled sind (Music-Videos, Shorts ohne Captions). Skript erkennt das automatisch und fällt zurück.

## Curiosity-Loop-Integration

Zwei Request-Typen, beide landen in `raw/requests/youtube-*.json`:

### Typ A — Tier-Upgrade auf existierendes Video

Compile sieht ein bereits ingestes Video reicht nicht für den Article-Bedarf:

- Tier-1-Article landet in `concepts/transformer-attention.md`. Compile sieht: "Video erwähnt visuell-heavy Beweis bei Min 14, Transcript zu vage" → erzeugt `raw/requests/youtube-upgrade-<video_id>.json` mit `{type: upgrade, video_id: ..., from_tier: 1, to_tier: 3, reason: "visual proof at 14:00 not captured in transcript"}`.
- "Wiki: Follow Curiosity Requests" → re-ingest mit höherem Tier → Article re-compiled.

Auto-resolvable, kein User-Eingriff nötig (außer Budget-Cap).

### Typ B — Neuer Ingest von einem unbekannten Video

Compile sieht eine Wissenslücke und vermutet: "ein YouTube-Video würde diesen Concept stärken":

```json
// raw/requests/youtube-search-<topic-slug>.json
{
  "type": "search",
  "topic": "diffusion model classifier-free guidance",
  "rationale": "concept article at concepts/diffusion-models.md mentions classifier-free guidance but has no source explaining the why; user has high signal on Yannic Kilcher / 3blue1brown style explanations",
  "preferred_channels": ["3blue1brown", "Yannic Kilcher", "AI Coffee Break"],
  "exclude_channels": [],
  "preferred_duration_s": [600, 2400],
  "tier_on_pick": 2,
  "status": "pending",
  "created_at": "..."
}
```

**Auflösung — zwei Modi:**

1. **Manual-Pick (Default, sicher):** Request landet in `raw/requests/`. Obsidian-Plugin (siehe obsidian-plugin.md) zeigt sie in der Sidebar als "Curiosity: searching for video on …". User klickt → Modal öffnet sich, User pastet URL aus Browser → Ingest läuft mit `tier_on_pick`. Sicher gegen Hallucination, der User kuratiert.

2. **Auto-Search (Opt-in):** `wiki follow-requests --auto-search-youtube`. Skript nutzt `yt-dlp 'ytsearchN:<topic>'` (z.B. N=10), bekommt URL+Title+Channel+Duration zurück, filtert gegen `preferred_channels` / `exclude_channels` / `preferred_duration_s`, zeigt Top-3 als Suggestion in `raw/suggestions/youtube-search-<topic>.yaml` (existing suggestion-queue, Plugin rendert das schon). User approved den Pick → Ingest. Kein autonomer Pick, immer User-in-the-Loop weil "wrong video" Garbage in Article erzeugt.

Schema für die Suggestion:

```yaml
# raw/suggestions/youtube-search-<topic>.yaml
type: youtube-search
topic: ...
rationale: ...
candidates:
  - url: https://youtube.com/watch?v=...
    title: "..."
    channel: "..."
    duration_s: 1234
    upload_date: 2025-...
    view_count: 245000
    score: 0.87  # hits preferred_channel + duration window
  - ...
actions:
  - {pick: candidate_0, tier: 2, status: pending}
  - {pick: candidate_1, tier: 2, status: pending}
  - {dismiss: true, status: pending}
```

Genau ein Action wird approved (per `execute-suggestions.py --approve`), die anderen werden auto-rejected. Symmetrie zu existing suggestion-queue.

**Hallucination-Guard:** Compile darf NICHT eine konkrete URL in den Request schreiben — nur `topic` + `preferred_channels`. URLs sind unverifizierbar aus LLM-Output (es würde plausible aber nicht-existente Video-IDs erfinden). Search/Pick muss durch yt-dlp ODER User passieren, beides verifizierbar.

**Budget-Cap pro Run** (analog email-collector): `youtube.curiosity_budget_usd: 0.50` — stoppt bei Erreichen. Tier-3-cloud zählt voll, Tier-3-local zählt 0¢ (kcma ist sunk-cost), Tier 0-2 zählt 0¢. Search-Requests selbst sind frei (yt-dlp). De-Dup gegen `raw/notes/youtube/*.json` Sidecars per `video_id` damit der Loop nicht das gleiche Video re-pickt.

### Dashboard-Surface

Beide Request-Typen (search + upgrade) sollen im `Dashboard.md` mit Approve/Reject-Buttons erscheinen — zusammen mit Curiosity-Requests aus *allen* anderen Collectors (email, screenshots, …). Generisches Design dafür: siehe `.ytstack/backlog/curiosity-dashboard.md`.

YouTube-spezifische Buttons in dieser generischen Surface:

| Button | CLI-Call |
|---|---|
| `yt-pick-N` | `wiki ingest-youtube --resolve-search <topic-slug> --pick <N> --tier <tier_on_pick>` |
| `yt-upgrade-<vid>-<provider>` | `wiki ingest-youtube --upgrade <vid> --tier 3 --provider <local\|cloud>` |

Reject/Dismiss läuft generisch über `wiki curiosity --dismiss <request-id>` und ist in der curiosity-dashboard-Surface zentral implementiert.

## Output-Schema (Sidecar)

```yaml
# raw/notes/youtube/<channel-slug>--<video-slug>.json
url: https://youtube.com/watch?v=...
video_id: dQw4w9WgXcQ
ingested_at: 2026-05-03T14:32:11Z
tier: 2
input_source: inbox  # inbox | clipper | plugin
user_note: "Spannend ab Min 12, Slides screenshoten"

# Tier 0
metadata:
  title: ...
  channel: ...
  duration_s: 1342
  upload_date: 2026-04-15
  chapters:
    - {start_s: 0, title: "Intro"}
    - {start_s: 120, title: "The trick"}
  description: ...
  tags: [...]

# Tier 1
transcript:
  language: en
  source: youtube-transcript-api  # | yt-dlp-fallback | none
  segments:
    - {start_s: 0.5, text: "..."}

# Tier 2
comments:
  fetched: 87
  filter: "like_count >= 5 OR is_creator_response"
  retained: 12
  items: [...]

# Tier 3 (only if tier >= 3)
gemini:
  model: gemini-2.5-flash-lite
  cost_usd: 0.021
  key_concepts: [...]
  visual_artifacts: [...]
  code_snippets: [...]
  corrections_to_audio: [...]
  chapter_summaries: [...]
  raw_response: |
    ...
```

Markdown-Begleitfile `<slug>.md` rendert obersichtlich für Obsidian + embeddet das Video iframe + linkt das Sidecar.

## Tools / OSS-First

Alles ist OSS, kein Eigenbau auf Application-Level:

- **`yt-dlp`** — Metadata, Subtitles-Fallback, Comments. Aktiv maintained, kein API-Key.
- **`youtube-transcript-api`** (jdepoix, PyPI v1.2.4 Jan 2026) — Default-Transcript-Reader, fallback auf yt-dlp.
- **Gemini API** (`google-genai` SDK) — Tier 3+. YouTube-URL-Direkt-Ingest aktuell Preview, sonst Files API.
- **Obsidian Web Clipper** + community-template — Pfad B, kein Eigenbau im Browser.

Adapter ist dünn: ein Skript `scripts/scan-youtube.py` mit `--tier {0..4}` flag, mit Default aus Config.

## Skript-Skeleton

```python
# scripts/scan-youtube.py
def ingest_one(url: str, tier: int, note: str | None) -> Sidecar:
    meta = ytdlp_metadata(url)                      # Tier 0
    if tier >= 1:
        meta.transcript = fetch_transcript(url)     # Tier 1
    if tier >= 2:
        meta.comments = fetch_comments(url)         # Tier 2
    if tier >= 3:
        meta.gemini = gemini_ingest(url, meta)      # Tier 3 (cost!)
    write_sidecar_and_markdown(meta)
    return meta

def parse_inbox(path: Path) -> list[(url, note, tier)]:
    # robust: bare URL, markdown link, mobile, shortlink, +note, +`tier: N`
    ...
```

CLI:
```
wiki ingest-youtube --inbox raw/inbox/youtube.md --default-tier 1
wiki ingest-youtube --url https://... --tier 3
wiki ingest-youtube --upgrade <video_id> --tier 3   # re-ingest existing
```

## Open Questions

- **Plugin-Command-Modal vs CLI-only:** Phase-1 nur CLI? Plugin-Modal kommt mit obsidian-plugin v2?
- **Sub-Sprache:** Default `en,de`? Wenn Channel Hindi/Spanisch ist? Auto-detect via metadata `categories` / `language`?
- **Re-Ingest beim Tier-Upgrade:** alten Sidecar überschreiben oder versionieren (`<slug>.json`, `<slug>.v2.json`)? Versionieren wenn Audit gewünscht, sonst überschreiben.
- **Privacy:** Description / Comments dürfen committed werden (öffentliche YouTube-Daten). Aber `user_note` ist privat → nie in `knowledge/` rendern, nur Sidecar.
- **Rate-Limits:** Bei 50-100 Videos in Inbox-Batch → exponential backoff zwischen yt-dlp-Calls. youtube-transcript-api ist fragil bei Hochfrequenz.
- **Compile-Folder-Routing:** YouTube-Lernkontent landet wo? `concepts/`? Oder neuer Toplevel `learning/` der parallel zu concepts ist? Diskussion separat.

## Reihenfolge / Priorisierung

1. **Tier 0+1 + Inbox-Parser** — kostenfrei, sofort nutzbar. ~3-4h.
2. **Tier 2 (Comments)** — billig dazuzunehmen wenn yt-dlp eh läuft. ~1h.
3. **Tier 3-local (gemma4 + ffmpeg-Frames)** — kostenfrei, kcma-d8 läuft eh. Default-Provider für Tier 3. ~4-5h + Eval.
4. **Tier 3-cloud (Gemini)** — Fallback wenn Ollama down oder explicit gewünscht. YouTube-URL-Direkt-Ingest ist Preview, sonst Files API. ~3h.
5. **Plugin-Command** — folgt obsidian-plugin v1, dann v2-Erweiterung.
6. **Tier 4 (Chapter-Deep-Dive)** — only on demand, kein eigener Slice nötig.
7. **Curiosity-Loop-Integration** — nach Tier-3-Lauf-Daten existieren, sonst rät man am Bedarf.

Alle Tiers sind unabhängig deploybar; Tier-Eskalation ist additiv und idempotent.

## Recherche-Quellen

- [youtube-transcript-api auf PyPI](https://pypi.org/project/youtube-transcript-api/) — v1.2.4, Jan 2026, Python 3.8-3.14, kein API-Key
- [jdepoix/youtube-transcript-api GitHub](https://github.com/jdepoix/youtube-transcript-api) — Source, Issues, Maintenance-Status
- [Gemini Video Understanding Docs](https://ai.google.dev/gemini-api/docs/video-understanding) — YouTube-URL-Preview, max 10 Videos/Request
- [Gemini API Pricing](https://ai.google.dev/gemini-api/docs/pricing) — 2.5-Flash-Lite/Flash/Pro Tarife
- [Make sense of YouTube videos using Gemini (IDinsight)](https://idinsight.github.io/tech-blog/blog/gemini_youtube/) — End-to-End Praxis-Beispiel mit Cost-Numbers
- [yt-dlp comments JSON output Issue](https://github.com/yt-dlp/yt-dlp/issues/2372) — Format der Kommentar-Extraktion
- [TubeSage Obsidian Plugin](https://github.com/rmccorkl/tubesage) — Reference-Pattern für Transcript+LLM-Summary in Obsidian
- [bramses/youtube-transcript-obsidian](https://github.com/bramses/youtube-transcript-obsidian) — minimaler Transcript-Importer (Fallback-Idee falls Plugin-Path bevorzugt)
- [Obsidian Web Clipper YouTube-Template](https://github.com/obsidian-community/web-clipper-templates/blob/main/templates/youtube-with-transcript-clipper.json) — Input-Pfad B ohne Eigenbau
