---
title: Dashboard Buttons (defs)
note: Transcluded from dashboard.md. Operator typically does not edit directly.
---

```meta-bind-button
label: 📝 Notiz
hidden: true
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
hidden: true
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
hidden: true
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
hidden: true
class: ""
tooltip: "Neue Meeting-Notiz in inbox/"
id: btn-meeting
style: default
actions:
  - type: command
    command: "QuickAdd: Neues Meeting"
```

```meta-bind-button
label: ▶️ Compile changed
hidden: true
class: ""
tooltip: "Run `wiki compile` — process raw/ + daily/ files whose hash changed."
id: btn-compile
style: primary
actions:
  - type: command
    command: "Shell commands: Wiki: compile (changed sources)"
```

```meta-bind-button
label: 🛡 Lint
hidden: true
class: ""
tooltip: "Run `wiki lint --structural-only`."
id: btn-lint
style: default
actions:
  - type: command
    command: "Shell commands: Wiki: lint (structural)"
```

```meta-bind-button
label: 🔄 Refresh stats
hidden: true
class: ""
tooltip: "Re-run dashboard_stats.py."
id: btn-refresh-stats
style: default
actions:
  - type: command
    command: "Shell commands: Wiki: refresh dashboard stats"
```

<!-- agent-button-defs:begin -->
```meta-bind-button
label: 🗓️ Daily digest
hidden: true
class: ""
tooltip: "Distill per-source captures into a single short digest."
id: btn-daily-digest
style: primary
actions:
  - type: command
    command: "Shell commands: Wiki: agent daily-digest"
```

```meta-bind-button
label: 📅 Summarize day
hidden: true
class: ""
tooltip: "Run summarize-day agent — refreshes today's Summary block in daily/."
id: btn-summarize-day
style: primary
actions:
  - type: command
    command: "Shell commands: Wiki: agent summarize-day"
```
<!-- agent-button-defs:end -->
