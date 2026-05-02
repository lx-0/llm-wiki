# 🗺️ Wiki Dashboard

> Home page for the vault. Auto-opens via the **Homepage** community plugin.
> Buttons use **Meta Bind**; capture flow uses **QuickAdd**; checkbox aggregation uses **Tasks**.

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

## 🔗 Quick access

[[knowledge/index|Index]] · [[AGENTS|Schema]] · [[knowledge/log|Compile log]]

---

## 📊 Vault stats

> Live charts. Aggregated from `knowledge/` + `daily/` frontmatter via `dataviewjs`. They update when files change. Requires the **Charts** and **Heatmap Calendar** community plugins.

### Source-type distribution

```dataviewjs
const pages = dv.pages('"knowledge"').filter(p => p.file.name !== "index" && p.file.name !== "log");
const counts = {};
for (const p of pages) {
  const t = p.type || "untyped";
  counts[t] = (counts[t] || 0) + 1;
}
const labels = Object.keys(counts);
const data = Object.values(counts);
if (labels.length === 0) {
  dv.paragraph("_No articles in `knowledge/` yet — the chart will appear after the first compile._");
} else if (typeof window.renderChart !== "function") {
  dv.paragraph("_Charts plugin not installed — Settings → Community Plugins → search **Charts**._");
} else {
  window.renderChart({
    type: "doughnut",
    data: { labels, datasets: [{ label: "Articles", data }] },
    options: { plugins: { legend: { position: "right" } } }
  }, this.container);
}
```

### Top 15 tags

```dataviewjs
const pages = dv.pages('"knowledge"').filter(p => p.file.name !== "index" && p.file.name !== "log");
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
if (sorted.length === 0) {
  dv.paragraph("_No tags found in compiled articles yet._");
} else if (typeof window.renderChart !== "function") {
  dv.paragraph("_Charts plugin not installed._");
} else {
  window.renderChart({
    type: "bar",
    data: {
      labels: sorted.map(([k]) => k),
      datasets: [{ label: "Articles", data: sorted.map(([, v]) => v) }]
    },
    options: { indexAxis: "y", plugins: { legend: { display: false } } }
  }, this.container);
}
```

### Articles per folder

```dataviewjs
const pages = dv.pages('"knowledge"').filter(p => p.file.name !== "index" && p.file.name !== "log");
const counts = {};
for (const p of pages) {
  const f = p.file.folder || "knowledge";
  counts[f] = (counts[f] || 0) + 1;
}
const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]);
if (sorted.length === 0) {
  dv.paragraph("_No articles yet._");
} else if (typeof window.renderChart !== "function") {
  dv.paragraph("_Charts plugin not installed._");
} else {
  window.renderChart({
    type: "bar",
    data: {
      labels: sorted.map(([k]) => k),
      datasets: [{ label: "Articles", data: sorted.map(([, v]) => v) }]
    },
    options: { plugins: { legend: { display: false } } }
  }, this.container);
}
```

### Inbound-link distribution

> How well-connected is the graph? A healthy LLM-wiki has most articles in the 1–10 inlinks range. Many zeros = orphan problem.

```dataviewjs
const pages = dv.pages('"knowledge"').filter(p => p.file.name !== "index" && p.file.name !== "log");
const buckets = { "0": 0, "1–2": 0, "3–5": 0, "6–10": 0, "11+": 0 };
for (const p of pages) {
  const n = p.file.inlinks.length;
  if (n === 0) buckets["0"]++;
  else if (n <= 2) buckets["1–2"]++;
  else if (n <= 5) buckets["3–5"]++;
  else if (n <= 10) buckets["6–10"]++;
  else buckets["11+"]++;
}
if (pages.length === 0) {
  dv.paragraph("_No articles yet._");
} else if (typeof window.renderChart !== "function") {
  dv.paragraph("_Charts plugin not installed._");
} else {
  window.renderChart({
    type: "bar",
    data: {
      labels: Object.keys(buckets),
      datasets: [{ label: "Articles", data: Object.values(buckets) }]
    },
    options: { plugins: { legend: { display: false } } }
  }, this.container);
}
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
