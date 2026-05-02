# Color Palette & Brand Style

**This is the single source of truth for all colors and brand-specific styles.** To customize diagrams for your own brand, edit this file — everything else in the skill is universal.

The default palette below is the one used for the diagrams shipped in this repo (warm-orange primary on a near-white canvas). Override per install if your brand differs.

---

## Shape Colors (Semantic)

Colors encode meaning, not decoration. Each semantic purpose has a fill/stroke pair.

| Semantic Purpose | Fill | Stroke |
|------------------|------|--------|
| Primary/Neutral | `#FFD8CB` | `#FC4E14` |
| Secondary | `#FFECB9` | `#FFBB38` |
| Tertiary | `#E5E5E5` | `#737373` |
| Start/Trigger | `#FFECB9` | `#92610F` |
| End/Success | `#E6F4EC` | `#1B7340` |
| Warning/Reset | `#FCEAE7` | `#C43D2E` |
| Decision | `#FFF4E0` | `#92610F` |
| AI/LLM | `#EFF6FF` | `#2563EB` |
| Inactive/Disabled | `#F5F5F5` | `#8C8C8C` (use dashed stroke) |
| Error | `#FCEAE7` | `#C43D2E` |

**Rule**: Always pair a darker stroke with a lighter fill for contrast.

---

## Text Colors (Hierarchy)

Use color on free-floating text to create visual hierarchy without containers.

| Level | Color | Use For |
|-------|-------|---------|
| Title | `#0A0A0A` | Section headings, major labels |
| Subtitle | `#FC4E14` | Subheadings, secondary labels (primary accent) |
| Body/Detail | `#737373` | Descriptions, annotations, metadata |
| On light fills | `#1A1A1A` | Text inside light-colored shapes |
| On dark fills | `#FFFFFF` | Text inside dark-colored shapes |

---

## Evidence Artifact Colors

Used for code snippets, data examples, and other concrete evidence inside technical diagrams.

| Artifact | Background | Text Color |
|----------|-----------|------------|
| Code snippet | `#1A1A1A` | Syntax-colored (language-appropriate) |
| JSON/data example | `#1A1A1A` | `#1B7340` (success green) |

---

## Default Stroke & Line Colors

| Element | Color |
|---------|-------|
| Arrows | Use the stroke color of the source element's semantic purpose |
| Structural lines (dividers, trees, timelines) | `#0A0A0A` (near-black) or `#737373` (slate) |
| Marker dots (fill + stroke) | `#FC4E14` (primary accent) |

---

## Background

| Property | Value |
|----------|-------|
| Canvas background | `#FFFFFF` |
