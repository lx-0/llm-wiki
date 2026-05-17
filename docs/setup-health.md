# Health intake setup

The health collector ingests biometric data in two phases:

- **Phase 1 — Oura Ring** (shipped, 2026-05-15). Daily REST pull of sleep / readiness / activity / HRV from `cloud.ouraring.com/v2`. Personal Access Token in Infisical. No setup beyond pasting the PAT into the operator's `<vault>/.wiki/config.yaml` under `personal.accounts.<id>.health.oura.pat_path`.
- **Phase 3a — Apple HealthKit via iOS Shortcut** (this document). Fills the gap Oura doesn't cover: **weight + body composition** (from Renpho-via-HealthKit) and **iPhone step count**. Apple Watch metrics are not in scope of 3a — the operator has none yet.

The two phases produce one rollup per date. The engine merges them on `date`: Oura wins for sleep / HRV / readiness; the Shortcut fills weight / body comp / steps.

Phase 2 (manual quarterly XML export) and Phase 3b (Health Auto Export $5 app) remain in the backlog at [`.ytstack/backlog/shipped/health-collector.md`](../.ytstack/backlog/shipped/health-collector.md). Pick 3a first because it's free, native, and produces real daily data.

## How Phase 3a works

```
iPhone Shortcut (daily 23:55)
   → reads HealthKit via Find/Get Health Sample actions
   → writes one JSON file per day to iCloud Drive
   → iCloud syncs to Mac within ~30 s–2 min
   → engine collector reads the JSON, merges with Oura
   → one .md per date in raw/notes/health/<year>/
```

The JSON file is the **engine contract**. The Shortcut MUST produce JSON that matches the shape below — the collector reads it strictly.

## 1. The JSON contract

The Shortcut writes one file per day named `YYYY-MM-DD.json`, overwriting if it already exists. Content:

```json
{
  "date": "2026-05-17",
  "source": "healthkit-shortcut",
  "weight_kg": 78.4,
  "body_fat_pct": 18.2,
  "lean_body_mass_kg": 60.1,
  "steps": 8412
}
```

Field rules:

- `date` — ISO `YYYY-MM-DD`, the date the data is *for* (the date the Shortcut runs).
- `source` — literal string `"healthkit-shortcut"`. Lets the engine distinguish from future Phase 2 XML drops.
- `weight_kg` — most-recent-ever weight sample in kilograms. Renpho writes to HealthKit on every weigh-in; if the operator hasn't weighed in for 3 days, this stays at the last known value. That's correct behavior.
- `body_fat_pct` — most-recent-ever, in percent (0-100, not 0-1).
- `lean_body_mass_kg` — most-recent-ever, in kilograms. Apple HealthKit has no standard `Bone Mass` or `Water Percentage` types — Renpho only writes weight + fat % + lean body mass to HealthKit even if those metrics show up in Renpho's own app.
- `steps` — sum of today's step samples (00:00 → now, device time).

If a sample doesn't exist (no weight ever logged, no steps today), the corresponding key may be omitted or set to `0`. The engine adapter treats missing values as "no data for that metric this day".

## 2. Pick an inbox path

Under iCloud Drive so iOS Shortcuts can write directly:

```bash
mkdir -p ~/Library/Mobile\ Documents/com~apple~CloudDocs/HealthIntake
```

On iOS, this folder shows up in the Files app as `iCloud Drive → HealthIntake`.

## 3. Build the iOS Shortcut

**iOS 26.4.x, Shortcuts app.** Action names are given English / Deutsch — the operator's iPhone is in German, the search box matches either. Tap + (top right) → New Shortcut.

The Shortcut has 11 actions (iOS 26 split what used to be "Get Latest Health Sample" into Find + Get Details, so each "what's my current X" needs two actions). Add them in order; each output is referenced by name in later actions (tap a variable slot, pick the right magic variable).

> **iOS 26 confirmed** (screenshot 2026-05-17): the Health category only has these query actions — `Health-Messungen suchen` (Find Health Samples), `Details von Health-Messung abrufen` (Get Details of Health Sample), `Health-Messung protokollieren` (Log — not used). There is no `Get Latest Health Sample` action anymore; "latest" is expressed as Find with Sort=Date desc + Limit=1.

### Action 1 — Get Current Date / Aktuelles Datum abrufen

- Search the action library for `Date` / `Datum` → pick **Get Current Date** / **Aktuelles Datum abrufen**.
- No parameters. The output is a Date value — keep its default name "Current Date" / "Aktuelles Datum".

### Action 2 — Format Date / Datum formatieren

- Search for `Format Date` / `Datum formatieren`.
- Date: *Current Date* (magic variable from Action 1).
- Date Format: **Custom** / **Eigene**, with format string `yyyy-MM-dd`.
- Time Format: **None** / **Keine**.
- Rename the output variable to `DateString` (tap on "Formatted Date" → Rename Variable / Variable umbenennen).

### Actions 3+4 — Latest Weight

**Action 3 — Find Health Samples (Weight) / Health-Messungen suchen (Gewicht)**

- Pick **Health-Messungen suchen**.
- Health Sample Type / Health-Messungstyp: **Weight** / **Gewicht**.
- Sort Order / Sortierreihenfolge: **Date** / **Datum**, **Descending** / **Absteigend**.
- Limit / Limit: **1**.
- No date filter.
- Rename output to `WeightSamples`.

If the action exposes a **Unit** / **Einheit** field: set to **kg**. If it doesn't (iOS 26 may have moved unit into Get Details below), leave it — we set it in Action 4.

**Action 4 — Get Details of Health Sample (Weight) / Details von Health-Messung abrufen**

- Pick **Details von Health-Messung abrufen**.
- Health Sample / Health-Messung: *WeightSamples*.
- Detail / Detail: **Value** / **Wert** (Apple's documented property name for the numeric measurement; the German label is likely **Wert**, possibly **Menge** — pick the one that the picker shows as numeric). Other Detail options exposed by this action: `unit`, `type`, `start date`, `end date`, `duration`, `source`, `name` — ignore those.
- Rename output to `WeightKg`.

> **Possible short path:** Apple's variable-types documentation states that magic variables expose their underlying properties via a chevron (›) when you tap them in a consuming action. If, inside Action 10 (Dictionary), tapping *WeightSamples* shows a chevron with a `Value`/`Wert` option, Actions 4 + 6 + 8 are all redundant — pick `WeightSamples → Value` directly. Try the short path first. If the chevron only shows the full sample as text (no property picker), keep the Get Details actions.

### Actions 5+6 — Latest Body Fat Percentage

Same shape as 3+4:

- **Find Health Samples**: Type = **Body Fat Percentage** / **Körperfettanteil**. Sort = Date desc. Limit = 1. Output → `FatSamples`.
- **Get Details of Health Sample**: Sample = *FatSamples*. Detail = **Value** / **Wert**. Output → `FatPct`.

Apple Health stores body fat as a fraction 0-1. Whether the picker outputs 0-1 or 0-100 depends on iOS internals. Note what you see — if the JSON shows `0.182` instead of `18.2`, we adjust the engine adapter (no need to fight Shortcuts).

### Actions 7+8 — Latest Lean Body Mass

Same shape:

- **Find Health Samples**: Type = **Lean Body Mass** / **Magere Körpermasse**. Sort = Date desc. Limit = 1. Output → `MuscleSamples`.
- **Get Details of Health Sample**: Sample = *MuscleSamples*. Detail = **Value** / **Wert**. Output → `MuscleKg`.

### Action 9 — Find Health Samples (Steps today) + Calculate Statistics

**9a — Find Health Samples / Health-Messungen suchen**

- Type / Typ: **Steps** / **Schritte**.
- Add a filter / Filter hinzufügen: **End Date is in the last** / **Enddatum liegt in den letzten** → **0** **Days** / **Tagen** (means today from 00:00).
- No limit, no sort (we'll sum next).
- Output → `StepsList`.

**9b — Calculate Statistics over Health Samples / Statistik über Health-Messungen berechnen**

- Search for `Statistik` or `Statistics`.
- Operation / Berechnung: **Sum** / **Summe**.
- Health Samples / Health-Messungen: *StepsList*.
- Output → `StepsSum`.

### Action 10 — Dictionary / Wörterbuch (build the JSON object)

- Pick **Dictionary** / **Wörterbuch**.
- Tap "Add new item" / "Neues Element hinzufügen" six times. The leftmost selector for each row picks the value type — match it exactly:

  | Key | Type / Typ | Value |
  |---|---|---|
  | `date` | Text | *DateString* |
  | `source` | Text | `healthkit-shortcut` (literal text) |
  | `weight_kg` | Number / Zahl | *WeightKg* |
  | `body_fat_pct` | Number / Zahl | *FatPct* |
  | `lean_body_mass_kg` | Number / Zahl | *MuscleKg* |
  | `steps` | Number / Zahl | *StepsSum* |

- Rename output to `HealthDict`.

### Action 11 — Save File / Datei sichern

- Search for `Save File` / `Datei sichern` (Files category / Dateien).
- File: *HealthDict*.
- Service: **iCloud Drive**.
- Destination Path / Zielpfad: `HealthIntake/` + *DateString* + `.json`
  - Build this in the path field by typing `HealthIntake/`, then inserting the *DateString* variable, then typing `.json`.
- Ask Where to Save / Speicherort erfragen: **Off** / **Aus**.
- Overwrite If File Exists / Datei ersetzen, falls vorhanden: **On** / **Ein**.

### Name the Shortcut

Top of the editor → tap the name field → `Capture HealthKit Daily`.

## 4. Daily trigger — Personal Automation

The Shortcut needs to run automatically at the end of each day so the JSON reflects a full day of steps.

In the Shortcuts app:

1. Bottom tab → **Automation**.
2. + (top right) → **New Automation**.
3. Pick **Time of Day**.
4. Time: `23:55`. Repeat: **Daily**.
5. Run Immediately: **On** (no notification, no confirmation tap — fully silent).
6. Next → search for `Run Shortcut` → **Run Shortcut**.
7. Shortcut: *Capture HealthKit Daily*.
8. Done.

### First run — permission prompts

The first time the Shortcut (or its automation) executes, iOS prompts twice:

1. **"Capture HealthKit Daily" wants to read Health Data** → Allow All Categories Used (Weight, Body Fat, Lean Body Mass, Steps) → Allow.
2. **"Capture HealthKit Daily" wants to save to iCloud Drive** → Allow.

After these prompts, runs are silent. If the operator denies either prompt, the Shortcut will fail silently on every subsequent run — there's no in-app indication other than the inbox staying empty.

To force a manual first run (recommended before relying on the automation): open the Shortcut in the Shortcuts app and tap ▶ at the top. Accept the prompts. Then check `iCloud Drive → HealthIntake/` for the file.

## 5. Verify on Mac

After the first run + a sync delay of 30 s – 2 min:

```bash
ls -la ~/Library/Mobile\ Documents/com~apple~CloudDocs/HealthIntake/
cat ~/Library/Mobile\ Documents/com~apple~CloudDocs/HealthIntake/2026-05-17.json
```

The file should be valid JSON matching the contract in section 1. If iCloud hasn't downloaded it eagerly:

```bash
brctl download "~/Library/Mobile Documents/com~apple~CloudDocs/HealthIntake/"
```

## 6. Wire into the engine (after adapter ships)

**Status as of 2026-05-17:** Adapter not yet implemented. This section is the forward-looking config contract — don't add the lines below before the engine adapter exists, it'll just be dead config.

In `<vault>/.wiki/config.yaml`, under the existing health account block:

```yaml
personal:
  accounts:
    <account-id>:
      health:
        kind: health-multi-source
        oura:
          pat_path: "agent-services/llm-wiki/OURA_PAT"
        healthkit:                                  # NEW for Phase 3a
          kind: healthkit-shortcut-inbox
          inbox_dir: "~/Library/Mobile Documents/com~apple~CloudDocs/HealthIntake"
```

When the adapter lands, `wiki collect health` will scan the inbox, merge each JSON with the Oura rollup for the same date, and move processed files into `<inbox_dir>/.processed/` (same pattern as voice).

## Troubleshooting

- **Shortcut runs but the inbox stays empty.** Almost always a permission prompt was missed on first run. Open the Shortcut and tap ▶ manually — iOS will re-prompt. If it doesn't re-prompt and still produces no file: Settings → Privacy & Security → Health → Shortcuts → confirm Read access for Weight, Body Fat Percentage, Lean Body Mass, Steps.
- **`Get Details of Health Sample` complains about input type** ("expected Sample, got List"). Insert a **Get Item from List** / **Element aus Liste abrufen** action between the Find and the Get Details: source = the `*Samples` list, item = **First Item** / **Erstes Element**, output → e.g. `WeightSample`. Then point Get Details at the single sample.
- **File appears in iCloud Drive but isn't valid JSON** (looks like `"date":"...","weight_kg":` with empty values, or has stray text). This means the Dictionary → Save File serialization didn't produce JSON. Fallback: replace Action 10 + 11 with a single **Text** action that contains a JSON template with magic-variable substitution, then **Save File** of the text. Template:
  ```
  {"date":"DateString","source":"healthkit-shortcut","weight_kg":WeightKg,"body_fat_pct":FatPct,"lean_body_mass_kg":MuscleKg,"steps":StepsSum}
  ```
  Substitute each capitalized name with its magic variable (using the numeric outputs from the Get Details actions, not the raw Sample lists). Watch out for: locale-formatted numbers (`78,4` instead of `78.4`) — if that happens, add **Format Number** / **Zahl formatieren** before each value reference, forcing decimal separator `.`.
- **iPhone wrote the file but Mac doesn't see it.** iCloud sync latency is 30 s – 2 min. Open the Files app on iPhone, confirm the file exists. If the Mac shows a cloud-icon next to the file, force download with `brctl download` (command in section 5).
- **Step count is way too low / zero.** The "Find Health Samples → End Date in last 0 Days" filter sometimes excludes samples from the current 5-minute window on iOS 26. If today's count looks off in evening runs, try changing the filter to **Start Date is today** instead, which is more inclusive.
- **Personal Automation didn't fire overnight.** Known iOS bug across multiple versions: time-triggered automations occasionally need re-authorization after iOS updates. Open Shortcuts → Automation → tap the automation → toggle it off and back on. No data is lost — the Shortcut just hasn't run; manually trigger it the next morning if the operator wants the missing day backfilled.
- **Weight / body fat shows as 0 in the JSON.** Renpho hasn't synced to Apple Health, OR the operator has Health categories disabled for Shortcuts read. Check: Health app → Browse → Body Measurements → Weight → confirm Renpho appears as a Data Source.
