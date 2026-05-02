---
name: excalidraw-diagram
description: >
  Create Excalidraw diagram JSON files that make visual arguments — workflows, architectures,
  concepts. Use when the user wants to visualize systems, processes, or ideas as .excalidraw files.
  Covers design methodology, section-by-section building, render-validate loop, and quality checklist.
metadata:
  author: llm-wiki contributors
  version: "1.0"
  category: design
  source: https://github.com/coleam00/excalidraw-diagram-skill
  notes: Adapted from Cole Medin's excalidraw-diagram-skill; color palette + naming generalized for OSS reuse.
compatibility: >
  File write access required. Rendering to PNG requires Python 3.11+, uv, and Playwright (chromium).
---

# Excalidraw Diagram Creator

Generate `.excalidraw` JSON files that **argue visually**, not just display information.

**Setup:** If the renderer hasn't been set up yet:
```bash
cd skills/excalidraw-diagram/references
uv sync
uv run playwright install chromium
```

## Customization

**All colors and brand-specific styles live in one file:** `references/color-palette.md`. Read it before generating any diagram and use it as the single source of truth for all color choices — shape fills, strokes, text colors, evidence artifact backgrounds, everything.

To make this skill produce diagrams in a different brand style, edit `color-palette.md`. Everything else in this file is universal design methodology and Excalidraw best practices.

---

## Core Philosophy

**Diagrams should ARGUE, not DISPLAY.**

A diagram isn't formatted text. It's a visual argument that shows relationships, causality, and flow that words alone can't express. The shape should BE the meaning.

**The Isomorphism Test**: If you removed all text, would the structure alone communicate the concept? If not, redesign.

**The Education Test**: Could someone learn something concrete from this diagram, or does it just label boxes? A good diagram teaches—it shows actual formats, real event names, concrete examples.

---

## Depth Assessment (Do This First)

Before designing, determine what level of detail this diagram needs:

### Simple/Conceptual Diagrams
Use abstract shapes when:
- Explaining a mental model or philosophy
- The audience doesn't need technical specifics
- The concept IS the abstraction (e.g., "separation of concerns")

### Comprehensive/Technical Diagrams
Use concrete examples when:
- Diagramming a real system, protocol, or architecture
- The diagram will be used to teach or explain (e.g., YouTube video)
- The audience needs to understand what things actually look like
- You're showing how multiple technologies integrate

**For technical diagrams, you MUST include evidence artifacts** (see below).

---

## Research Mandate (For Technical Diagrams)

**Before drawing anything technical, research the actual specifications.**

If you're diagramming a protocol, API, or framework:
1. Look up the actual JSON/data formats
2. Find the real event names, method names, or API endpoints
3. Understand how the pieces actually connect
4. Use real terminology, not generic placeholders

Bad: "Protocol" -> "Frontend"
Good: "AG-UI streams events (RUN_STARTED, STATE_DELTA, A2UI_UPDATE)" -> "CopilotKit renders via createA2UIMessageRenderer()"

**Research makes diagrams accurate AND educational.**

---

## Evidence Artifacts

Evidence artifacts are concrete examples that prove your diagram is accurate and help viewers learn. Include them in technical diagrams.

**Types of evidence artifacts** (choose what's relevant to your diagram):

| Artifact Type | When to Use | How to Render |
|---------------|-------------|---------------|
| **Code snippets** | APIs, integrations, implementation details | Dark rectangle + syntax-colored text (see color palette for evidence artifact colors) |
| **Data/JSON examples** | Data formats, schemas, payloads | Dark rectangle + colored text (see color palette) |
| **Event/step sequences** | Protocols, workflows, lifecycles | Timeline pattern (line + dots + labels) |
| **UI mockups** | Showing actual output/results | Nested rectangles mimicking real UI |
| **Real input content** | Showing what goes IN to a system | Rectangle with sample content visible |
| **API/method names** | Real function calls, endpoints | Use actual names from docs, not placeholders |

The key principle: **show what things actually look like**, not just what they're called.

---

## Multi-Zoom Architecture

Comprehensive diagrams operate at multiple zoom levels simultaneously.

### Level 1: Summary Flow
A simplified overview showing the full pipeline or process at a glance.

### Level 2: Section Boundaries
Labeled regions that group related components. These create visual "rooms" that help viewers understand what belongs together.

### Level 3: Detail Inside Sections
Evidence artifacts, code snippets, and concrete examples within each section. This is where the educational value lives.

**For comprehensive diagrams, aim to include all three levels.**

### Bad vs Good

| Bad (Displaying) | Good (Arguing) |
|------------------|----------------|
| 5 equal boxes with labels | Each concept has a shape that mirrors its behavior |
| Card grid layout | Visual structure matches conceptual structure |
| Icons decorating text | Shapes that ARE the meaning |
| Same container for everything | Distinct visual vocabulary per concept |
| Everything in a box | Free-floating text with selective containers |

---

## Container vs. Free-Floating Text

**Not every piece of text needs a shape around it.** Default to free-floating text. Add containers only when they serve a purpose.

| Use a Container When... | Use Free-Floating Text When... |
|------------------------|-------------------------------|
| It's the focal point of a section | It's a label or description |
| It needs visual grouping with other elements | It's supporting detail or metadata |
| Arrows need to connect to it | It describes something nearby |
| The shape itself carries meaning (decision diamond, etc.) | Typography alone creates sufficient hierarchy |
| It represents a distinct "thing" in the system | It's a section title, subtitle, or annotation |

**The container test**: For each boxed element, ask "Would this work as free-floating text?" If yes, remove the container.

---

## Design Process (Do This BEFORE Generating JSON)

### Step 0: Assess Depth Required
- **Simple/Conceptual**: Abstract shapes, labels, relationships
- **Comprehensive/Technical**: Concrete examples, code snippets, real data

**If comprehensive**: Do research first. Look up actual specs, formats, event names, APIs.

### Step 1: Understand Deeply
Read the content. For each concept, ask:
- What does this concept **DO**? (not what IS it)
- What relationships exist between concepts?
- What's the core transformation or flow?
- **What would someone need to SEE to understand this?**

### Step 2: Map Concepts to Patterns
For each concept, find the visual pattern that mirrors its behavior:

| If the concept... | Use this pattern |
|-------------------|------------------|
| Spawns multiple outputs | **Fan-out** (radial arrows from center) |
| Combines inputs into one | **Convergence** (funnel, arrows merging) |
| Has hierarchy/nesting | **Tree** (lines + free-floating text) |
| Is a sequence of steps | **Timeline** (line + dots + free-floating labels) |
| Loops or improves continuously | **Spiral/Cycle** (arrow returning to start) |
| Is an abstract state or context | **Cloud** (overlapping ellipses) |
| Transforms input to output | **Assembly line** (before -> process -> after) |
| Compares two things | **Side-by-side** (parallel with contrast) |
| Separates into phases | **Gap/Break** (visual separation between sections) |

### Step 3: Ensure Variety
For multi-concept diagrams: **each major concept must use a different visual pattern**. No uniform cards or grids.

### Step 4: Sketch the Flow
Before JSON, mentally trace how the eye moves through the diagram. There should be a clear visual story.

### Step 5: Generate JSON
Only now create the Excalidraw elements. **See below for how to handle large diagrams.**

### Step 6: Render & Validate (MANDATORY)
After generating the JSON, you MUST run the render-view-fix loop until the diagram looks right. See the **Render & Validate** section below.

---

## Large / Comprehensive Diagram Strategy

**For comprehensive or technical diagrams, build the JSON one section at a time.** Do NOT attempt to generate the entire file in a single pass — token limits and quality both demand section-by-section building.

### The Section-by-Section Workflow

**Phase 1: Build each section**

1. **Create the base file** with the JSON wrapper (`type`, `version`, `appState`, `files`) and the first section of elements.
2. **Add one section per edit.** Each section gets its own dedicated pass.
3. **Use descriptive string IDs** (e.g., `"trigger_rect"`, `"arrow_fan_left"`) so cross-section references are readable.
4. **Namespace seeds by section** (e.g., section 1 uses 100xxx, section 2 uses 200xxx) to avoid collisions.
5. **Update cross-section bindings** as you go.

**Phase 2: Review the whole**

After all sections are in place, read through the complete JSON and check:
- Are cross-section arrows bound correctly on both ends?
- Is the overall spacing balanced?
- Do IDs and bindings all reference elements that actually exist?

**Phase 3: Render & validate**

Run the render-view-fix loop from the Render & Validate section.

### What NOT to Do

- **Don't generate the entire diagram in one response.** You will hit the output token limit and produce truncated, broken JSON.
- **Don't use a coding agent** to generate the JSON. The agent won't have sufficient context about the skill's rules.
- **Don't write a Python generator script.** Hand-crafted JSON with descriptive IDs is more maintainable.

---

## Visual Pattern Library

### Fan-Out (One-to-Many)
Central element with arrows radiating to multiple targets. Use for: sources, PRDs, root causes, central hubs.

### Convergence (Many-to-One)
Multiple inputs merging through arrows to single output. Use for: aggregation, funnels, synthesis.

### Tree (Hierarchy)
Parent-child branching with connecting lines and free-floating text (no boxes needed). Use `line` elements for the trunk and branches, free-floating text for labels.

### Spiral/Cycle (Continuous Loop)
Elements in sequence with arrow returning to start. Use for: feedback loops, iterative processes.

### Cloud (Abstract State)
Overlapping ellipses with varied sizes. Use for: context, memory, conversations, mental states.

### Assembly Line (Transformation)
Input -> Process Box -> Output with clear before/after. Use for: transformations, processing, conversion.

### Side-by-Side (Comparison)
Two parallel structures with visual contrast. Use for: before/after, options, trade-offs.

### Gap/Break (Separation)
Visual whitespace or barrier between sections. Use for: phase changes, context resets, boundaries.

### Lines as Structure
Use lines (type: `line`, not arrows) as primary structural elements instead of boxes:
- **Timelines**: Vertical/horizontal line with small dots (10-20px ellipses) at intervals, free-floating labels beside each dot
- **Tree structures**: Vertical trunk line + horizontal branch lines, with free-floating text labels
- **Dividers**: Thin dashed lines to separate sections
- **Flow spines**: A central line that elements relate to

Lines + free-floating text often creates a cleaner result than boxes + contained text.

---

## Shape Meaning

Choose shape based on what it represents — or use no shape at all:

| Concept Type | Shape | Why |
|--------------|-------|-----|
| Labels, descriptions, details | **none** (free-floating text) | Typography creates hierarchy |
| Section titles, annotations | **none** (free-floating text) | Font size/weight is enough |
| Markers on a timeline | small `ellipse` (10-20px) | Visual anchor, not container |
| Start, trigger, input | `ellipse` | Soft, origin-like |
| End, output, result | `ellipse` | Completion, destination |
| Decision, condition | `diamond` | Classic decision symbol |
| Process, action, step | `rectangle` | Contained action |
| Abstract state, context | overlapping `ellipse` | Fuzzy, cloud-like |
| Hierarchy node | lines + text (no boxes) | Structure through lines |

**Rule**: Default to no container. Add shapes only when they carry meaning. Aim for <30% of text elements to be inside containers.

---

## Color as Meaning

Colors encode information, not decoration. Every color choice should come from `references/color-palette.md`.

**Key principles:**
- Each semantic purpose (start, end, decision, AI, error, etc.) has a specific fill/stroke pair
- Free-floating text uses color for hierarchy (titles, subtitles, details)
- Evidence artifacts (code snippets, JSON examples) use their own dark background + colored text scheme
- Always pair a darker stroke with a lighter fill for contrast

**Do not invent new colors.** If a concept doesn't fit an existing semantic category, use Primary/Neutral or Secondary.

---

## Modern Aesthetics

### Roughness
- `roughness: 0` — Clean, crisp edges. **Default for most use cases.**
- `roughness: 1` — Hand-drawn, organic feel. Use for brainstorming/informal diagrams.

### Stroke Width
- `strokeWidth: 1` — Thin, elegant. Good for lines, dividers, subtle connections.
- `strokeWidth: 2` — Standard. Good for shapes and primary arrows.
- `strokeWidth: 3` — Bold. Use sparingly for emphasis.

### Opacity
**Always use `opacity: 100` for all elements.**

### Small Markers Instead of Shapes
Use small dots (10-20px ellipses) as timeline markers, bullet points, connection nodes, visual anchors.

---

## Layout Principles

### Hierarchy Through Scale
- **Hero**: 300x150 - visual anchor, most important
- **Primary**: 180x90
- **Secondary**: 120x60
- **Small**: 60x40

### Whitespace = Importance
The most important element has the most empty space around it (200px+).

### Flow Direction
Guide the eye: typically left->right or top->bottom for sequences, radial for hub-and-spoke.

### Connections Required
Position alone doesn't show relationships. If A relates to B, there must be an arrow.

---

## Text Rules

**CRITICAL**: The JSON `text` property contains ONLY readable words.

```json
{
  "id": "myElement1",
  "text": "Start",
  "originalText": "Start"
}
```

Settings: `fontSize: 16`, `fontFamily: 3`, `textAlign: "center"`, `verticalAlign: "middle"`

---

## JSON Structure

```json
{
  "type": "excalidraw",
  "version": 2,
  "source": "https://excalidraw.com",
  "elements": [...],
  "appState": {
    "viewBackgroundColor": "#ffffff",
    "gridSize": 20
  },
  "files": {}
}
```

## Element Templates

See `references/element-templates.md` for copy-paste JSON templates for each element type (text, line, dot, rectangle, arrow). Pull colors from `references/color-palette.md` based on each element's semantic purpose.

---

## Render & Validate (MANDATORY)

You cannot judge a diagram from JSON alone. After generating or editing the Excalidraw JSON, you MUST render it to PNG, view the image, and fix what you see — in a loop until it's right.

### How to Render

```bash
# Full render
cd skills/excalidraw-diagram/references && uv run python render_excalidraw.py <path-to-file.excalidraw>

# Render + crop a specific region (Excalidraw coordinates)
cd skills/excalidraw-diagram/references && uv run python render_excalidraw.py <path-to-file.excalidraw> --crop "x,y,width,height"
```

Full render outputs a PNG next to the `.excalidraw` file. With `--crop`, an additional `*-crop.png` is saved showing only the specified region.

**IMPORTANT for large diagrams:** The full PNG may be too large for the LLM to read details. Use `--crop` to verify specific sections. Look up element coordinates from the JSON (`"x"`, `"y"`, `"width"`, `"height"` fields) and crop that region with ~100px padding around it.

### The Loop

**1. Render & View** — Run the render script, then Read the PNG. **For large diagrams: also crop and verify each changed section individually.**

**2. Audit against your original vision** — Before looking for bugs, compare the rendered result to what you designed in Steps 1-4. Ask:
- Does the visual structure match the conceptual structure you planned?
- Does each section use the pattern you intended?
- Does the eye flow through the diagram in the order you designed?
- Is the visual hierarchy correct?
- For technical diagrams: are evidence artifacts readable and properly placed?

**3. Check for visual defects (use `--crop` to verify each changed section):**
- Text clipped by or overflowing its container
- Text or shapes overlapping other elements — **verify by checking element y+height doesn't exceed next element's y**
- Arrows crossing through elements instead of routing around them
- Arrows landing on the wrong element or pointing into empty space
- Labels floating ambiguously
- Uneven spacing between elements that should be evenly spaced
- Text too small to read at the rendered size
- Overall composition feels lopsided or unbalanced

**3b. Coordinate overlap check (MANDATORY for edits to existing diagrams):**
When you modify element sizes (e.g., making a box taller for more text), verify that downstream elements don't overlap. For each modified element:
1. Read its new `y + height` from the JSON
2. Check that the next element's `y` is at least 15px below
3. If overlapping, shift all downstream elements by the difference
4. Re-check arrows that connect shifted elements (start/end positions)

**4. Fix** — Edit the JSON to address everything you found.

**5. Re-render & re-view** — Run the render script again and Read the new PNG.

**6. Repeat** — Keep cycling until the diagram passes both the vision check and the defect check. Typically takes 2-4 iterations.

### When to Stop

The loop is done when:
- The rendered diagram matches the conceptual design
- No text is clipped, overlapping, or unreadable
- Arrows route cleanly and connect to the right elements
- Spacing is consistent and the composition is balanced
- You'd be comfortable showing it to someone without caveats

### First-Time Setup
```bash
cd skills/excalidraw-diagram/references
uv sync
uv run playwright install chromium
```

---

## Quality Checklist

### Depth & Evidence (Check First for Technical Diagrams)
1. **Research done**: Did you look up actual specs, formats, event names?
2. **Evidence artifacts**: Are there code snippets, JSON examples, or real data?
3. **Multi-zoom**: Does it have summary flow + section boundaries + detail?
4. **Concrete over abstract**: Real content shown, not just labeled boxes?
5. **Educational value**: Could someone learn something concrete from this?

### Conceptual
6. **Isomorphism**: Does each visual structure mirror its concept's behavior?
7. **Argument**: Does the diagram SHOW something text alone couldn't?
8. **Variety**: Does each major concept use a different visual pattern?
9. **No uniform containers**: Avoided card grids and equal boxes?

### Container Discipline
10. **Minimal containers**: Could any boxed element work as free-floating text instead?
11. **Lines as structure**: Are tree/timeline patterns using lines + text rather than boxes?
12. **Typography hierarchy**: Are font size and color creating visual hierarchy?

### Structural
13. **Connections**: Every relationship has an arrow or line
14. **Flow**: Clear visual path for the eye to follow
15. **Hierarchy**: Important elements are larger/more isolated

### Technical
16. **Text clean**: `text` contains only readable words
17. **Font**: `fontFamily: 3`
18. **Roughness**: `roughness: 0` for clean/modern (unless hand-drawn style requested)
19. **Opacity**: `opacity: 100` for all elements
20. **Container ratio**: <30% of text elements should be inside containers

### Visual Validation (Render Required)
21. **Rendered to PNG**: Diagram has been rendered and visually inspected
22. **No text overflow**: All text fits within its container
23. **No overlapping elements**: Shapes and text don't overlap unintentionally
24. **Even spacing**: Similar elements have consistent spacing
25. **Arrows land correctly**: Arrows connect to intended elements
26. **Readable at export size**: Text is legible in the rendered PNG
27. **Balanced composition**: No large empty voids or overcrowded regions
