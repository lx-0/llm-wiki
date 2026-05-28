---
cssclasses: [wiki-dashboard]
---

# 🗺️ Wiki Dashboard

> Home page. Layout: scan top in 5 seconds → scroll to your mode (Personal / Work / AI) → open collapsed callouts only for triage.

## ➕ Capture

`BUTTON[btn-note]` `BUTTON[btn-idea]` `BUTTON[btn-question]` `BUTTON[btn-meeting]`

## 🔥 Today

> Only the actionable. If nothing's here, you're clean.

### Overdue + due today

```tasks
not done
(path includes knowledge/people) OR (path includes knowledge/projects) OR (path includes knowledge/areas)
((due before today) OR (due on today))
sort by due
limit 15
short mode
```

### Engine alerts

```dataviewjs
const stats = dv.page("_dashboard-stats");
const lint = dv.page("_dashboard-lint");
const alerts = [];
const failed = stats?.failed_flushes ?? 0;
const pending = stats?.pending_compiles ?? 0;
const warnings = stats?.lint_warnings ?? 0;
if (failed > 0) alerts.push(`> [!warning] **${failed}** failed flush(es) — see [[_dashboard-stats]]`);
if (pending > 0) alerts.push(`> [!info] **${pending}** pending compile(s) — click 🔧 → Compile changed`);
if (warnings > 0) alerts.push(`> [!warning] **${warnings}** lint warning(s) — expand 🛡 Lint below`);
if (alerts.length === 0) {
  dv.paragraph("> [!success] Engine green · last compile " + (stats?.last_compile_ts ?? "—"));
} else {
  for (const a of alerts) dv.paragraph(a);
}
```

---

## 🏠 Personal

### Active Areas

```dataview
TABLE WITHOUT ID
  file.link AS "Area",
  status AS "Status",
  dateformat(file.mtime, "yyyy-MM-dd") AS "Updated"
FROM "knowledge/areas"
WHERE domain = "personal" AND status = "active"
SORT file.mtime DESC
```

### Themed sections from your brain

> Auto-aggregated from `knowledge/concepts/personal-*` and `ai-ideas-*` (operator-authored, `compile_role: source-and-final`). Each → wikilink, content lives at source.

```dataview
TABLE WITHOUT ID
  file.link AS "Theme",
  kind AS "Kind",
  join(filter(tags, (t) => t != "personal"), ", ") AS "Tags"
FROM "knowledge/concepts"
WHERE author = "alex" AND compile_role = "source-and-final" AND contains(tags, "personal")
SORT kind ASC, file.name ASC
```

### Personal tasks (open, undated)

```tasks
not done
(path includes knowledge/people) OR (path includes knowledge/projects) OR (path includes knowledge/areas)
no due date
filter by function task.file.frontmatter?.domain === "personal" || (task.file.path.includes("personal-") && !task.file.frontmatter?.domain)
limit 15
short mode
```

---

## 🏢 Work

### Active Areas (company)

```dataview
TABLE WITHOUT ID
  file.link AS "Area",
  status AS "Status",
  dateformat(file.mtime, "yyyy-MM-dd") AS "Updated"
FROM "knowledge/areas"
WHERE domain = "company" AND status = "active"
SORT file.mtime DESC
```

> Empty? Consider seeding the obvious ones: CTO-Hat, llm-wiki Maintenance, Active Customer engagements, Fundraise.

### Active projects

```dataview
TABLE WITHOUT ID
  file.link AS "Project",
  status AS "Status",
  dateformat(file.mtime, "yyyy-MM-dd") AS "Updated"
FROM "knowledge/projects"
WHERE (domain = "company") OR (!domain AND contains(tags, "yesterday"))
SORT file.mtime DESC
LIMIT 12
```

### Recent meetings

```dataview
TABLE WITHOUT ID
  file.link AS "Meeting",
  dateformat(file.cday, "yyyy-MM-dd") AS "Date"
FROM "raw/transcripts/jamie" OR "raw/transcripts/gmeet"
SORT file.cday DESC
LIMIT 8
```

### Work tasks (this week)

```tasks
not done
(path includes knowledge/people) OR (path includes knowledge/projects)
due after today
due before in 7 days
sort by due
limit 15
short mode
```

---

## 🤖 AI / Tech

### Tech-platform projects

```dataview
TABLE WITHOUT ID
  file.link AS "Project",
  dateformat(file.mtime, "yyyy-MM-dd") AS "Updated"
FROM "knowledge/projects"
WHERE domain = "ai" OR contains(tags, "openclaw") OR contains(tags, "paperclip") OR contains(tags, "fleet") OR contains(tags, "agentic-foundation")
SORT file.mtime DESC
LIMIT 10
```

### AI Predictions & Future Thoughts

```dataview
TABLE WITHOUT ID
  file.link AS "Note",
  dateformat(file.mtime, "yyyy-MM-dd") AS "Updated"
FROM "raw/notes/longform"
WHERE startswith(file.name, "ai-ideas-")
SORT file.mtime DESC
```

### Recent AI-concept compiles

```dataview
TABLE WITHOUT ID
  file.link AS "Concept",
  dateformat(file.mtime, "yyyy-MM-dd") AS "Updated"
FROM "knowledge/concepts"
WHERE contains(tags, "ai") OR contains(tags, "openclaw") OR contains(tags, "agent")
SORT file.mtime DESC
LIMIT 10
```

---

## 🔧 Run

`BUTTON[btn-compile]` `BUTTON[btn-lint]` `BUTTON[btn-refresh-stats]` `BUTTON[btn-daily-digest]`

## 🔗 Quick access

[[knowledge/index|Index]] · [[knowledge.base|Browse knowledge]] · [[AGENTS|Schema]] · [[knowledge/people/alex|Self]]

---

> [!info]- 📊 Stats & Charts
> ![[_dashboard-stats]]
>
> ```dataviewjs
> // Hidden until expanded. Charts only render when this callout is opened.
> const cs = getComputedStyle(document.body);
> const _v = (n, f) => (cs.getPropertyValue(n) || f).trim();
> const pal = [_v("--color-blue","#5b8def"), _v("--color-orange","#e89954"), _v("--color-green","#5fb364"), _v("--color-purple","#9b6dc7"), _v("--color-cyan","#4ec5d4")];
> if (typeof window.renderChart !== "function") { dv.paragraph("_Charts plugin not installed._"); return; }
> const pages = dv.pages('"knowledge"').filter(p => p.file.name !== "index" && p.file.name !== "log");
> const grid = this.container.createDiv();
> grid.style.cssText = "display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:1rem;margin:0.5rem 0;";
> function cell(title) { const c = grid.createDiv(); const h = c.createEl("h4",{text:title}); h.style.margin="0 0 0.5rem 0"; const w = c.createDiv(); w.style.cssText="position:relative;height:240px;"; return w; }
> // Source-type distribution
> { const counts={}; for (const p of pages) { const t=p.type||"untyped"; counts[t]=(counts[t]||0)+1; }
>   window.renderChart({type:"doughnut",data:{labels:Object.keys(counts),datasets:[{data:Object.values(counts),backgroundColor:Object.keys(counts).map((_,i)=>pal[i%pal.length])}]},options:{maintainAspectRatio:false,plugins:{legend:{position:"right",labels:{color:_v("--text-normal","#ddd"),font:{size:11}}}}}}, cell("By type")); }
> // Domain breakdown (M013)
> { const counts={personal:0,company:0,ai:0,meta:0,unscoped:0}; for (const p of pages) { const d=p.domain; if (d && counts[d]!==undefined) counts[d]++; else if (!d) counts.unscoped++; }
>   window.renderChart({type:"doughnut",data:{labels:Object.keys(counts),datasets:[{data:Object.values(counts),backgroundColor:["#5fb364","#5b8def","#9b6dc7","#888","#444"]}]},options:{maintainAspectRatio:false,plugins:{legend:{position:"right",labels:{color:_v("--text-normal","#ddd"),font:{size:11}}}}}}, cell("By domain")); }
> ```

> [!warning]- 🛡 Lint triage
> ```dataviewjs
> const lint = dv.page("_dashboard-lint");
> const queues = [
>   { key: "orphans_count", title: "Orphans", section: "Orphans" },
>   { key: "stale_count", title: "Stale", section: "Stale" },
>   { key: "missing_backlinks_count", title: "Missing backlinks", section: "Missing backlinks" },
>   { key: "failed_flushes_count", title: "Failed flushes", section: "Failed flushes" },
> ];
> for (const q of queues) {
>   const n = lint?.[q.key] ?? 0;
>   if (n === 0) dv.paragraph(`> [!success] ${q.title} (0)`);
>   else dv.paragraph(`> [!warning]- ${q.title} (${n})\n> ![[_dashboard-lint#${q.section}]]`);
> }
> ```

> [!info]- 📥 Inbox triage
> ```dataview
> TABLE WITHOUT ID
>   file.link AS "Note",
>   type AS "Type",
>   dateformat(file.mtime, "yyyy-MM-dd HH:mm") AS "Modified"
> FROM "inbox"
> SORT file.mtime DESC
> ```

> [!info]- ⏳ Pending review
> ```dataview
> TABLE WITHOUT ID
>   file.link AS "Note",
>   type AS "Type",
>   agent AS "Agent"
> FROM "" AND -"raw" AND -"daily" AND -"knowledge" AND -"Templates"
> WHERE status = "review"
> SORT file.mtime DESC
> LIMIT 20
> ```

> [!info]- 🏝️ Orphan notes
> ```dataview
> LIST
> FROM ""
> WHERE length(file.inlinks) = 0
>   AND !contains(file.folder, ".obsidian")
>   AND !contains(file.folder, "Templates")
>   AND !contains(file.folder, "knowledge")
>   AND !contains(file.folder, "raw")
>   AND !contains(file.folder, "daily")
>   AND !contains(file.folder, "imported")
>   AND !startswith(file.name, "_dashboard")
>   AND file.name != "dashboard"
>   AND file.name != "AGENTS"
>   AND file.name != "README"
> SORT file.folder ASC, file.name ASC
> LIMIT 25
> ```

> [!info]- 🗂 MOCs
> ```dataview
> LIST
> FROM "knowledge/MOCs"
> SORT file.name ASC
> ```

> [!info]- 🤖 Agents
> <!-- agent-buttons:begin -->
`BUTTON[btn-daily-digest]` `BUTTON[btn-dream-cycle]` `BUTTON[btn-summarize-day]`
<!-- agent-buttons:end -->

---

%% Button definitions live in _dashboard-buttons.md (auto-seeded). Transcluded here so the main dashboard stays focused on content. %%

![[_dashboard-buttons]]
