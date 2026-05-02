---
cssclasses: [wiki-dashboard]
---

# 🗺️ Wiki Dashboard

> Home page for the vault. Auto-opens via the **Homepage** community plugin.
> Buttons use **Meta Bind**; capture flow uses **QuickAdd**; checkbox aggregation uses **Tasks**.
> Layout requires the **wiki-dashboard** CSS snippet (Settings → Appearance → CSS snippets).

## ➕ Capture

```meta-bind-button
label: 📝 Notiz
hidden: false
class: ""
tooltip: "Neue Notiz in inbox/"
id: btn-note
style: primary
actions:
  - type: command
    command: "QuickAdd: Neue Notiz"
```

```meta-bind-button
label: 💡 Idee
hidden: false
class: ""
tooltip: "Neue Idee in inbox/"
id: btn-idea
style: default
actions:
  - type: command
    command: "QuickAdd: Neue Idee"
```

```meta-bind-button
label: ❓ Frage
hidden: false
class: ""
tooltip: "Neue Frage (für Curiosity Loop) in inbox/"
id: btn-question
style: default
actions:
  - type: command
    command: "QuickAdd: Neue Frage"
```

```meta-bind-button
label: 🤝 Meeting
hidden: false
class: ""
tooltip: "Neue Meeting-Notiz in inbox/"
id: btn-meeting
style: default
actions:
  - type: command
    command: "QuickAdd: Neues Meeting"
```

---

## ⚡ Engine status

![[_dashboard-stats]]

## 🔧 Run

> One-click ops. Each button executes a `wiki <subcommand>` via the **Shell commands** plugin. Output appears as a notification.

```meta-bind-button
label: ▶️ Compile changed
hidden: false
class: ""
tooltip: "Run `wiki compile` — process raw/ + daily/ files whose hash changed since last run."
id: btn-compile
style: primary
actions:
  - type: command
    command: "Shell commands: Wiki: compile (changed sources)"
```

```meta-bind-button
label: 🔁 Compile all
hidden: false
class: ""
tooltip: "Run `wiki compile --all` — force-recompile every source. Ask for confirmation."
id: btn-compile-all
style: destructive
actions:
  - type: command
    command: "Shell commands: Wiki: compile (all sources, force)"
```

```meta-bind-button
label: 🛡 Lint
hidden: false
class: ""
tooltip: "Run `wiki lint --structural-only` — orphan / broken-link / type-mismatch checks (no LLM)."
id: btn-lint
style: default
actions:
  - type: command
    command: "Shell commands: Wiki: lint (structural)"
```

```meta-bind-button
label: 🔄 Refresh stats
hidden: false
class: ""
tooltip: "Re-run dashboard_stats.py — recompute pending counts, lint warnings, total cost."
id: btn-refresh-stats
style: default
actions:
  - type: command
    command: "Shell commands: Wiki: refresh dashboard stats"
```

## 🔗 Quick access

[[knowledge/index|Index]] · [[AGENTS|Schema]] · [[knowledge/log|Compile log]]

---

## 📊 Vault stats

> Live charts. Aggregated from `knowledge/` + `daily/` frontmatter via `dataviewjs`. Updates when files change. Requires **Charts** + **Heatmap Calendar** plugins.

```dataviewjs
// Single dataviewjs builds the entire 4-chart grid. Why one block instead of four:
// Obsidian wraps every top-level markdown block in its own `.el-X` container in
// reading mode, which prevents raw-HTML wrappers like `<div class="grid">…</div>`
// from forming a real DOM hierarchy with their children — the grid container ends
// up empty and charts render as orphaned siblings. Building the grid in JS makes
// the DOM hierarchy independent of Obsidian's per-block wrapping.
//
// The IIFE wrapper is required because Dataview executes the script body
// at top level (no enclosing function), so a bare `return` would throw
// `SyntaxError: Illegal return statement`.

;(() => {

const cs = getComputedStyle(document.body);
const _v = (name, fallback) => (cs.getPropertyValue(name) || fallback).trim();
const textColor = _v("--text-normal", "#ddd");
const gridColor = _v("--background-modifier-border", "#444");
const accent = _v("--color-accent", "#7c8cff");
const palette = [
  _v("--color-blue", "#5b8def"),
  _v("--color-orange", "#e89954"),
  _v("--color-green", "#5fb364"),
  _v("--color-purple", "#9b6dc7"),
  _v("--color-cyan", "#4ec5d4"),
  _v("--color-red", "#d65b5b"),
  _v("--color-yellow", "#d6b85b"),
  _v("--color-pink", "#d36fb8"),
];
const ok = palette[2], warn = palette[6], danger = palette[5];

if (typeof window.renderChart !== "function") {
  dv.paragraph("_Charts plugin not installed — Settings → Community Plugins → search **Charts**._");
  return;
}

// Grid container — styles inlined so the layout doesn't depend on the
// CSS snippet being enabled. minmax(280px, 1fr) gives a smooth 1→2→3→4
// column flow as the window widens; the `wiki-dashboard.css` snippet
// handles disabling Obsidian's Readable Line Length so this grid actually
// gets a wide container to lay out into.
const grid = this.container.createDiv({cls: "wiki-chart-grid"});
Object.assign(grid.style, {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
  gap: "1rem",
  alignItems: "start",
  margin: "0.5rem 0 1.5rem 0",
});

function cell(title, note) {
  const c = grid.createDiv({cls: "wiki-chart-cell"});
  c.style.minWidth = "0";
  const h = c.createEl("h3", {text: title});
  h.style.margin = "0 0 0.25rem 0";
  if (note) {
    const n = c.createEl("p", {text: note});
    n.style.cssText = "margin: 0 0 0.5rem 0; color: var(--text-muted); font-size: 0.85rem;";
  }
  const wrap = c.createDiv();
  wrap.style.cssText = "position: relative; height: 280px;";
  return wrap;
}

const pages = dv.pages('"knowledge"').filter(p => p.file.name !== "index" && p.file.name !== "log");

// 1) Source-type distribution (doughnut)
{
  const counts = {};
  for (const p of pages) {
    let t = p.type;
    if (!t) {
      const folder = p.file.folder || "";
      const segs = folder.split("/").filter(Boolean);
      t = segs.length > 1 ? segs[segs.length - 1] : "knowledge-root";
    }
    counts[t] = (counts[t] || 0) + 1;
  }
  const labels = Object.keys(counts);
  const data = Object.values(counts);
  const target = cell("Source-type distribution");
  if (labels.length === 0) {
    target.textContent = "No articles in knowledge/ yet — appears after first compile.";
  } else {
    window.renderChart({
      type: "doughnut",
      data: { labels, datasets: [{ label: "Articles", data,
        backgroundColor: labels.map((_, i) => palette[i % palette.length]),
        borderColor: gridColor, borderWidth: 1 }] },
      options: { maintainAspectRatio: false,
        plugins: { legend: { position: "right", labels: { color: textColor } } } }
    }, target);
  }
}

// 2) Top 15 tags (horizontal bar)
{
  const tagCounts = {};
  for (const p of pages) {
    const tags = p.tags ?? [];
    const arr = Array.isArray(tags) ? tags : [tags];
    for (const t of arr) {
      const key = String(t);
      if (!key) continue;
      tagCounts[key] = (tagCounts[key] || 0) + 1;
    }
  }
  const sorted = Object.entries(tagCounts).sort((a, b) => b[1] - a[1]).slice(0, 15);
  const target = cell("Top 15 tags");
  if (sorted.length === 0) {
    target.textContent = "No tags found in compiled articles yet.";
  } else {
    window.renderChart({
      type: "bar",
      data: { labels: sorted.map(([k]) => k),
        datasets: [{ label: "Articles", data: sorted.map(([, v]) => v),
          backgroundColor: accent, borderColor: accent, borderWidth: 1 }] },
      options: { maintainAspectRatio: false, indexAxis: "y",
        plugins: { legend: { display: false } },
        scales: { x: { ticks: { color: textColor }, grid: { color: gridColor } },
                  y: { ticks: { color: textColor }, grid: { color: gridColor } } } }
    }, target);
  }
}

// 3) Article freshness (bar)
{
  const now = Date.now();
  const day = 24 * 60 * 60 * 1000;
  const buckets = { "<7d": 0, "7–30d": 0, "30–90d": 0, "90d+": 0 };
  for (const p of pages) {
    const ageDays = (now - p.file.mtime.toMillis()) / day;
    if (ageDays < 7) buckets["<7d"]++;
    else if (ageDays < 30) buckets["7–30d"]++;
    else if (ageDays < 90) buckets["30–90d"]++;
    else buckets["90d+"]++;
  }
  const colors = [ok, ok, warn, danger];
  const target = cell("Article freshness", "Recent = healthy. Lots of 90d+ = content going stale.");
  if (pages.length === 0) {
    target.textContent = "No articles yet.";
  } else {
    window.renderChart({
      type: "bar",
      data: { labels: Object.keys(buckets),
        datasets: [{ label: "Articles", data: Object.values(buckets),
          backgroundColor: colors, borderColor: gridColor, borderWidth: 1 }] },
      options: { maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { x: { ticks: { color: textColor }, grid: { color: gridColor } },
                  y: { ticks: { color: textColor }, grid: { color: gridColor } } } }
    }, target);
  }
}

// 4) Inbound-link distribution (bar)
{
  const buckets = { "0": 0, "1–2": 0, "3–5": 0, "6–10": 0, "11+": 0 };
  for (const p of pages) {
    const n = p.file.inlinks.length;
    if (n === 0) buckets["0"]++;
    else if (n <= 2) buckets["1–2"]++;
    else if (n <= 5) buckets["3–5"]++;
    else if (n <= 10) buckets["6–10"]++;
    else buckets["11+"]++;
  }
  const colors = [danger, warn, ok, ok, ok];
  const target = cell("Inbound-link distribution", "Healthy = most articles in 1–10 inlinks. Lots of 0 = orphan problem.");
  if (pages.length === 0) {
    target.textContent = "No articles yet.";
  } else {
    window.renderChart({
      type: "bar",
      data: { labels: Object.keys(buckets),
        datasets: [{ label: "Articles", data: Object.values(buckets),
          backgroundColor: colors, borderColor: gridColor, borderWidth: 1 }] },
      options: { maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { x: { ticks: { color: textColor }, grid: { color: gridColor } },
                  y: { ticks: { color: textColor }, grid: { color: gridColor } } } }
    }, target);
  }
}

})();
```

### Daily activity (current year)

> One cell per day. Darker = more session activity captured to `daily/YYYY-MM-DD.md`. Requires the **Heatmap Calendar** plugin.

```dataviewjs
const dailyPages = dv.pages('"daily"');
const entries = [];
for (const p of dailyPages) {
  const name = p.file.name;
  if (/^\d{4}-\d{2}-\d{2}$/.test(name)) {
    const sizeKb = Math.max(1, Math.ceil(p.file.size / 1000));
    entries.push({ date: name, intensity: Math.min(sizeKb, 5) });
  }
}
if (entries.length === 0) {
  dv.paragraph("_No daily logs yet — captured automatically by the session-end / pre-compact hooks._");
} else if (typeof renderHeatmapCalendar !== "function") {
  dv.paragraph("_Heatmap Calendar plugin not installed — Settings → Community Plugins → search **Heatmap Calendar**._");
} else {
  renderHeatmapCalendar(this.container, {
    year: new Date().getFullYear(),
    colors: { default: ["#9be9a8", "#40c463", "#30a14e", "#216e39"] },
    entries
  });
}
```

---

## 📥 Inbox triage

> New notes that haven't been classified yet. Move into `raw/<type>/` once you know where they belong; the compiler picks them up from there.

```dataview
TABLE WITHOUT ID
  file.link AS "Note",
  type AS "Type",
  status AS "Status",
  dateformat(file.mtime, "yyyy-MM-dd HH:mm") AS "Modified"
FROM "inbox"
SORT file.mtime DESC
```

## ⏳ Pending review

> Notes with `status: review` — typically agent output waiting for human approval, revise, or reject. Engine-managed folders (`raw/`, `daily/`, `knowledge/`) are excluded; they're not edit-targets.

```dataview
TABLE WITHOUT ID
  file.link AS "Note",
  type AS "Type",
  agent AS "Agent",
  dateformat(file.mtime, "yyyy-MM-dd HH:mm") AS "Modified"
FROM "" AND -"raw" AND -"daily" AND -"knowledge" AND -"Templates"
WHERE status = "review"
SORT file.mtime DESC
LIMIT 30
```

## ✅ Open tasks

> Aggregated checkboxes from working files only. Engine-managed substrates (`raw/` is immutable ground-truth, `daily/` is the session audit log, `knowledge/` is LLM output) are excluded — checkboxes there aren't yours to act on.

```tasks
not done
path does not include raw/
path does not include daily/
path does not include knowledge/
path does not include Templates/
group by folder
limit 25
short mode
```

---

## 📚 Recently compiled

```dataview
TABLE WITHOUT ID
  file.link AS "Article",
  dateformat(file.mtime, "yyyy-MM-dd HH:mm") AS "Updated",
  file.folder AS "Folder",
  length(file.outlinks) AS "Out-links"
FROM "knowledge"
WHERE file.name != "index" AND file.name != "log"
SORT file.mtime DESC
LIMIT 15
```

## 🌟 Top concepts

> The most-linked articles in `knowledge/`. These are the load-bearing nodes of the graph — when one of these gets stale, downstream articles drift.

```dataview
TABLE WITHOUT ID
  file.link AS "Article",
  length(file.inlinks) AS "Inlinks",
  file.folder AS "Folder"
FROM "knowledge"
WHERE file.name != "index" AND file.name != "log" AND length(file.inlinks) > 0
SORT length(file.inlinks) DESC
LIMIT 10
```

## 🕐 Recent daily logs

```dataview
TABLE WITHOUT ID
  file.link AS "Day",
  dateformat(file.mtime, "yyyy-MM-dd HH:mm") AS "Last session",
  file.size AS "Bytes"
FROM "daily"
SORT file.name DESC
LIMIT 7
```

## 📦 Recent raw additions

```dataview
TABLE WITHOUT ID
  file.link AS "Source",
  dateformat(file.cday, "yyyy-MM-dd") AS "Added",
  file.folder AS "Folder"
FROM "raw"
SORT file.cday DESC
LIMIT 10
```

---

## 🏝️ Orphan notes

> Working files with no inbound links. Either link them from a relevant article, archive, or delete. Engine-managed folders (`raw/` ground-truth, `daily/` audit log, `knowledge/` LLM output) are excluded — orphans there are expected, not actionable.

```dataview
LIST
FROM ""
WHERE length(file.inlinks) = 0
  AND !contains(file.folder, ".obsidian")
  AND !contains(file.folder, "Templates")
  AND !contains(file.folder, "knowledge")
  AND !contains(file.folder, "raw")
  AND !contains(file.folder, "daily")
  AND !startswith(file.name, "_dashboard-stats")
  AND file.name != "dashboard"
  AND file.name != "AGENTS"
  AND file.name != "README"
SORT file.folder ASC, file.name ASC
LIMIT 30
```

---

> [!info] How this dashboard works
> - **Capture buttons** trigger QuickAdd captures that drop a typed note into `inbox/` from a template in `Templates/`. Edit the templates if you want different default frontmatter or sections.
> - **Engine status** transcludes `_dashboard-stats.md`, regenerated by `scripts/dashboard_stats.py` after every `wiki flush`.
> - **Inbox / Pending review / Tasks** are live Dataview queries — they update as soon as files change.
> - The lower table block is the same data the agent sees through `knowledge/index.md`, but rendered for human navigation.
> - Triage queues, charts (Dataview Charts plugin), and topic MOCs land in M003 slices S02–S04.
