---
created: 2026-05-03
status: deferred
context: M003 / S08 (informal — screenshot-intake review on 2026-05-03)
related: scripts/scan-screenshots.py, prompts/scan_screenshots_vision.md, prompts/compile_main.md
---

# Screenshots-Intake — Tier 3+4 Backlog

Tier 1+2 (PNG-Embed im Batch-Report, source_screenshots im Compile-Frontmatter, Vault-Sidecars mit raw_response, HOME-Sidecar als Slim-Marker) sind 2026-05-03 implementiert (commit folgt). Die folgenden Items adressieren Output-Qualität und Audit-Tiefe — orthogonal zum Closed-Loop-Fix.

## Tier 3 — Output-Qualität

### E. App-Name-Normalisierung via Ollama JSON-Schema enum

**Problem.** Das Vision-LLM (gemma4:e4b) gibt im `app:` Feld inkonsistent kapitalisierte Strings zurück: `Web Browser` / `web browser` / `Web Application` / `web application` / `Code Editor` / `Code Editor/IDE` / `VS Code`. Tag-/App-Statistiken im Dashboard verschmieren weil der gleiche App-Typ unter mehreren Namen gezählt wird.

**Lösung.** Im Vision-Prompt einen `format`-JSON-Schema-Constraint mit `app: {"type": "string", "enum": [...]}` mitgeben. Liste der bekannten Apps:

```python
KNOWN_APPS = [
    "VS Code", "Cursor", "Obsidian", "Firefox", "Chrome", "Safari",
    "Slack", "Terminal", "iTerm2", "Mail", "Calendar", "Finder",
    "Web Browser (other)", "Web App (other)", "IDE (other)",
    "Native App (other)", "Unknown",
]
```

Implementation: `ollama_client.chat_vision` erweitert um `format=` Parameter (analog zu `chat_schema`), Schema in `scan_screenshots_vision.md` aufnehmen. Ollama erzwingt enum am Token-Level → keine Drift mehr.

**Caveat.** Aus `KNOWLEDGE.md` (Hard-won learnings → Ollama structured output): "Item-level type:object is not always honored" und "minLength is ignored". Enum funktioniert aber zuverlässig. Dennoch defensive Read-Side-Normalisierung beibehalten (`str(app).strip().lower()`).

**Aufwand:** ~1h. Test: 20 Screenshots mit aktuellem Modell verarbeiten, App-Drift-Quote vor/nach messen.

---

### F. Project-Hallucination-Guard

**Problem.** Beobachtetes Verhalten in `screenshots-2026-04-29T1812.md`: gemma4 fabricated `project: DocFlow Systems` für einen Web-Browser-Screenshot. Das ist kein realer Projektname — das LLM rät, weil das Prompt sagt "look for product names". User-`project_examples` aus `CONFIG.personal.project_examples` werden im Prompt als Hint gelistet, das LLM ignoriert die Closed-World-Annahme.

**Lösung.** Drei Optionen:

1. **Strenger Schema-Constraint (empfohlen).** `project: {"type": ["string", "null"], "enum": [*CONFIG.personal.project_examples, None]}`. Closed world + null-fallback. Bei unbekannten Projekten zwingt das Schema das Modell auf `null`.
2. **Post-hoc Validation.** Nach Parse: `if parsed["project"] not in CONFIG.personal.project_examples: parsed["project"] = None`. Einfacher, weniger Token-Effizient (LLM generiert weiterhin frei, wir verwerfen). Aber robust falls Schema-Enum mit langer Liste das Modell verwirrt.
3. **Confidence-Floor.** Zusätzliches `project_confidence: number` Feld. Drop wenn < 0.7. Fragwürdig — gemma4 kalibriert schlecht.

Empfehlung: **(1) wenn project_examples ≤ 30 Einträge, sonst (2)**. Threshold dokumentieren.

**Aufwand:** ~30min Code + ~1h Eval auf bestehender Batch.

---

## Tier 4 — Nice-to-have

### G. Per-Run Vision-Log

**Problem.** Wenn das Modell drifted (neue Version, neue Tag-Patterns), gibt es keine Möglichkeit das historisch zu auditen. Vault-Sidecars haben `raw_response` für Einzelbilder, aber kein Run-übergreifendes Aggregat.

**Lösung.** Pro Run: `<vault>/raw/notes/screenshots/_runs/<slug>.json` mit:

```json
{
  "slug": "screenshots-2026-05-03T0908",
  "started_at": "...",
  "finished_at": "...",
  "model": "gemma4:e4b",
  "ollama_url": "...",
  "screenshots": [
    {"file": "Screenshot ....png", "ts": "...", "tokens": 187, "duration_s": 38.0, "relevance": "keep", "raw_response": "..."},
    ...
  ],
  "stats": {"keep": 45, "ephemeral": 5, "errors": 0}
}
```

Vorteil: machine-readable, eignet sich für Schema-Drift-Analyse-Skripte.

**Aufwand:** ~30min. Reine Append-Operation, kein Schema-Risiko.

---

### H. Symlink-Alternative zu PNG-Copy

**Problem.** Tier-1-A kopiert jede PNG in den Vault (`raw/notes/screenshots/img/`). Bei 50/run und 1MB/PNG = ~50MB pro Run iCloud-Sync. Für lokale Vaults ist das egal, für iCloud-Vaults nicht.

**Lösung.** Statt `shutil.copy2` einen Symlink: `(IMG_DIR / src.name).symlink_to(src)`. Obsidian rendert Symlinks zu Bildern in den meisten Fällen korrekt (Live Preview + Reading Mode getestet — siehe Issue [forum.obsidian.md/symlinks](https://forum.obsidian.md/t/symlinks-and-vault-portability)).

**Caveats.**
- iCloud syncht Symlinks NICHT als Files → auf Mobile/iPad sind die Bilder weg.
- Wenn User das Original-PNG aus `~/Screenshots/` löscht, ist es im Vault auch weg.
- Cross-platform: NTFS/exFAT-Vault-Mounts mögen Symlinks oft nicht.

Daher: nur als Opt-in via `--use-symlinks` Flag oder `config.yaml.scan_screenshots.image_strategy: copy|symlink`.

**Aufwand:** ~30min Code, ~1h Test auf Mobile-Sync.

---

## Reihenfolge / Priorisierung

1. **F** (Project-Hallucination-Guard) — größter Quality-Win, weil Project-Drift die Folder-Routing-Heuristik im Compile vergiftet.
2. **E** (App-Enum) — dashboard-stat-Kosmetik.
3. **G** (Vision-Log) — only when drift is actually suspected.
4. **H** (Symlink) — only if iCloud quota becomes a real concern (defer until 1 GB+ in `img/`).

Alle vier sind unabhängig voneinander und können einzeln gemerged werden.
