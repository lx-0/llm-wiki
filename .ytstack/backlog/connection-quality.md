---
name: Connection quality & graph value — research synthesis + 5-action roadmap
description: Research synthesis from 30+ community sources (Karpathy, Cole Medin, Matuschak, Joel Chan, LLM-Wiki v2, Obsidian plugin landscape). Diagnoses 6 failure modes for sparse LLM-wiki graphs and proposes a prioritized 5-step action list — retro-link pass, prompt rewrite with quota+non-obviousness, Graph Analysis Link Prediction, MOCs as anchors, typed-relation frontmatter + lint.
type: research
origin: vault-observation
created: 2026-05-02
---

# LLM-Wiki Connection Quality & Obsidian Graph Value

Synthesis of community best practices for LLM-driven personal wikis (Karpathy-pattern) and graph-view utility in Obsidian. Compiled from Karpathy primary sources, Cole Medin's claude-memory-compiler, follow-up critiques (LLM Wiki v2, ghelburlabs, Hacker News), PKM theory (Matuschak, Milo), discourse-graphs (Joel Chan), and Obsidian plugin reviews.

## TL;DR

The "connections aren't giving much value" complaint is shared by **almost everyone running this pattern**. Karpathy's gist barely treats cross-references as a first-class concern — they're a side-effect of compile, only auditable via lint. Independent re-implementations converge on the same diagnosis: **untyped, LLM-generated `[[wikilinks]]` produce a hairball graph that looks impressive but doesn't generate insight.** The fix is layered — better link semantics, MOC anchors, graph-view tuning, a dedicated link-discovery prompt pass, lower bar for what counts as a connection.

A 263:46 concept-to-connection ratio (≈5.7:1) is on the **sparse end**. A Hacker News showcase from `vbarsoum` reported 210 concepts with ~4,600 cross-references (~22:1) — ~4× higher link density.

---

## 1. The Karpathy Pattern Itself

**Origin.** Karpathy's tweet went up April 3, 2026; gist `442a6bf...` April 5, 2026. Architecture: three layers (raw immutable / wiki LLM-maintained / schema CLAUDE.md). Three operations: **ingest, query, lint**.

**On connections.** Karpathy treats them as emergent, not designed. Cross-references are a thing the LLM "just does" during ingest; the lint step is supposed to catch what's missing:

> "ask the LLM to health-check the wiki. Look for: contradictions between pages, stale claims that newer sources have superseded, **orphan pages with no inbound links, important concepts mentioned but lacking their own page, missing cross-references**, data gaps that could be filled with a web search."

That's the **only** place in Karpathy's design where link quality is addressed. There is **no separate "connections" article type** — connections are inline `[[wikilinks]]` between concepts. The `knowledge/connections/` folder is a Cole Medin–era addition.

**Cole Medin's `claude-memory-compiler`** is the first popular Claude Code-native implementation. His AGENTS.md defines three article types — concepts, connections, qa — with this rule:

> "[Connections are] Created when a conversation reveals a non-obvious relationship. Cross-cutting synthesis linking 2+ concepts."

The phrase "non-obvious" is the most-cited single failure mode in the literature: LLMs default to linking obvious things (every "AI" article links to every other "AI" article) and miss the actual load-bearing bridges.

---

## 2. Why the Graph Feels Sparse — The Common Failure Modes

**Mode A — Hub domination ("star structure").** Obsidian's default graph "exhibits a 'star structure' where all the nodes that connect to the main 'central' one look the same." One mega-node ("AI", "Agent", "Knowledge") absorbs all the links and the graph degenerates into spokes around 3–5 hubs.

**Mode B — Under-linking from prompt timidity.** Compile prompts most people use ("only link if highly relevant", "be conservative about backlinks") collapse recall. LLM Wiki v2 makes the typed-relations argument: "Not all connections are equal. 'uses,' 'depends on,' 'contradicts,' 'caused,' 'fixed,' 'supersedes' carry different semantic weight." Without that vocabulary, the model picks the safe small set.

**Mode C — Append-only drift.** "**Real intelligence rewrites.**" Karpathy's pattern updates pages, but most implementations only **append** — when Article 50 is created, the system doesn't go back and add backlinks from articles 1–49 to it. Result: early articles are perpetually under-linked relative to later ones.

**Mode D — Markdown-link / wikilink mismatch.** If the LLM emits `[label](path.md)` instead of `[[path]]`, Obsidian's backlink and graph engine **silently drops the edge**.

**Mode E — Orphan accumulation = signal of decay, not just sparseness.** "Orphan notes usually signal missing engagement — you saved the idea but never connected it to anything else." For an LLM wiki, an orphan rate above ~5% means the compile prompt isn't integrating new articles.

**Mode F — Concept granularity wrong.** Matuschak: *Evergreen notes should be atomic.* If articles are too coarse (one giant `agentic-foundation-skill-system.md` covering 8 sub-ideas) they consume what should be 8 separate atomic concepts and 20+ links between them.

**Diagnostic — sparse vs. starved.** The ratio test from working systems is **15–25 links per concept**. this vault is at **~5.7×**. Not "not enough data yet" — definitely under-linked. 263 articles is well past the threshold where a healthy graph should have triple the edge count.

---

## 3. Concepts vs. Connections — The Architectural Debate

**Camp 1: inline wikilinks only (Karpathy, Matuschak).**

> "If we push ourselves to add lots of links between our notes, that makes us think expansively about what other concepts might be related... linking creates pressure to think carefully about how ideas relate to each other." — Andy Matuschak

Dense lateral linking inside concept notes IS the connection layer. No separate "connection article" — a well-written evergreen note IS a connection.

**Camp 2: typed relationships (Joel Chan / discourse graphs).** Discourse Graphs use **typed nodes** (Question, Claim, Evidence, Source) and **typed relations** (supports, opposes, informs, derivedFrom). Argument: untyped wikilinks all look the same in the graph view; "supports" vs "opposes" produces a graph you can actually reason over.

**Camp 3: dedicated connection articles (Cole Medin, this vault).** A connection article = a small synthesis note explaining **why** two concepts relate. Pros: forces explanation, becomes a reusable cite-able artifact, anchors the relationship as a node (which fixes hub-domination by introducing intermediate nodes). Cons: doubles surface area, drift risk, can become orphaned itself.

**Verdict — hybrid.**
- Inline `[[wikilinks]]` are the default — every concept article should have **5–15** of them.
- Dedicated **connection articles only when the relationship has its own substance** ("X enables Y because Z"). If you can't write 3 sentences explaining the relationship that aren't already in either concept, it's an inline link.
- **Type the connection in frontmatter** (`relation_type: enables | contradicts | depends_on | refines | example_of`) even if Obsidian doesn't natively render it — the Graph Link Types plugin will, and it makes the graph color-coded and legible.

---

## 4. Obsidian Graph View Tuning

Native graph view is widely considered ornamental: "graph views appearing in community showcases are primarily 'abstract paintings' rather than productivity tools." Settings and plugins that make it diagnostic:

**Native settings that matter:**
- **Color groups by folder.** `path:knowledge/concepts/` one color, `path:knowledge/connections/` another, `path:knowledge/projects/` a third. Instantly shows which clusters are concept-heavy vs connection-starved.
- **Filter `-path:daily/`** to remove daily-note noise from the global graph.
- **Search-as-filter:** type any tag/string into the graph search bar and only matching nodes light up — converts the graph from "static painting" to "ad-hoc query result."
- **Local graph + depth=2** is the most useful day-to-day. Depth 1 is just backlinks; depth 2 reveals second-order neighbors and is where insight surfaces.

**Plugins worth installing (by leverage):**

1. **Graph Analysis (SkepticMystic)** — runs **Co-Citations** (2nd-order backlinks: "what notes are cited together with note X?"), **Link Prediction** (Adamic-Adar / Common Neighbours suggests *missing* links the LLM should have created), **Community Detection** (label propagation), **Similarity** (Jaccard on neighbors). Link Prediction is the killer feature for a sparse LLM-wiki — tells you exactly which concept pairs the LLM probably should have connected.
2. **InfraNodus** — proper network science. Surfaces **structural gaps** (clusters with no bridges), **betweenness centrality**, **modularity**. Their pitch: "calculates distances between these clusters and reveal the structural gaps in the knowledge graph... blind holes in the discourse useful for generating novel connections."
3. **Smart Connections (brianpetro)** — local embeddings; shows semantically-related notes regardless of explicit links. Becomes a "missing link suggester" — every concept has a sidebar of 5 candidate links the LLM didn't make. ~4,400 GitHub stars, 786K downloads as of Jan 2026.
4. **Juggl** — alternative layouts (force-directed, concentric, **hierarchical**). Hierarchical mode is the killer: "the most-linked notes hold a higher position over those with fewer links." Hub-domination immediately visible.
5. **Graph Link Types** — renders typed link relations (`enables`, `contradicts`) as colored/labeled edges. Combine with Camp-2 typed-link strategy.

---

## 5. Prompt Engineering for Richer Connections

Highest-leverage intervention. Default Karpathy compile prompt is timid. Patterns that work:

**A. Two-pass compile (single most-recommended improvement).**
- Pass 1 — **Discovery, index-only**: feed only `index.md` (one-line summaries) and ask: "Identify 3–5 connection candidates among existing concepts: (1) cross-cutting themes that recur across unrelated sources, (2) implicit relationships between concepts that lack a direct link, (3) contradictions, (4) gaps where many concepts imply a missing concept."
- Pass 2 — **Synthesis**: for each candidate, deep-read the concept articles and either add inline backlinks or write a connection article.

**B. Explicit non-obviousness mandate.** "Non-obvious" alone is too vague. Better: "For each new concept, find the 3 *most surprising* existing concepts it relates to. A relationship is surprising if it bridges two sub-topics that share no obvious tag, folder, or vocabulary. **Reject relationships any reasonable reader would already infer from the concept titles alone.**"

**C. Few-shot examples.** Show the LLM 3–5 paired examples of *good* connection articles (one-paragraph synthesis with a load-bearing claim) vs *bad* ones (restating both concepts, generic "both relate to AI"). Prompt-only systems consistently underperform until few-shot is added.

**D. Quota the link count.** "Each new concept article must link to **at least 5** existing concepts. If you cannot find 5, list the 3 closest candidates and explain why each is too distant — output goes to the lint queue." Forcing the LLM to justify *why not* surfaces near-misses.

**E. Retro-link pass on existing articles.** When a new concept is added, run a separate prompt over the **last N concepts** (e.g. 30): "Should any of these articles link to the new concept `<X>`? If yes, add the wikilink in the most natural sentence." Fixes append-only drift (Mode C).

**F. Typed-relation extraction in frontmatter.** Even without the discourse-graph plugin, have the LLM emit `relations: [{type: enables, target: agentic-foundation-skill-system}, {type: contradicts, target: agi-level-3-urgency}]`. Creates a queryable layer with Dataview, graph-renderable later.

---

## 6. MOCs as Graph Anchors

A MOC (Map of Content, Nick Milo / LYT) is **a curated note containing a structured list of `[[wikilinks]]` to a thematic neighborhood** with short annotations. Not a tag, not a folder, not an auto-generated index. Milo: MOCs function as "tag, folder, and curator simultaneously." Key insight (seqis/ObsidianMOC): "find notes with 10 or more connections as candidates for Maps of Content." MOCs aren't created top-down — they emerge bottom-up from concepts that already attract many links.

**Concrete shape (example for an agent-architecture MOC):**

```markdown
---
type: moc
created: 2026-05-02
---
# Agentic Foundation MOC

The architecture and operating model for self-organizing agent systems.

## Identity & Isolation
- [[agent-environment-isolation]] — why each agent gets its own runtime
- [[agent-identity-architecture]] — token-scoped vs. role-scoped
- [[agent-services-strict-decoupling]] — the cloud-repo boundary rule

## Workflow & PR
- [[agentic-foundation-pr-workflow]]
- [[agent-fleet-github-operations]]
- [[ceo-agent-instructions-path-bug]]  (recurring issue)

## Skills System
- [[agentic-foundation-skill-system]]
- [[ambassador-training-model]]

## Open questions
- [[agi-level-3-urgency]] — does this still hold given X?
```

Graph-view effect: the MOC becomes a high-betweenness bridge node, and the spokes become a visible cluster instead of a hairball. Color the `mocs/` folder a distinct color and the structure pops. **MOC-of-MOCs** at the top: a single `knowledge/mocs/_home.md` linking every MOC. Becomes the home note and the strongest anchor.

---

## 7. Diagnostic — Data Foundation or Linking Strategy?

**Linking strategy, not data foundation.** Heuristics:

- **263 concepts is plenty.** Karpathy's working wiki was ~100 articles when he posted. this vault is 2.6×.
- **5.7× link-per-concept is below median.** Working systems report 15–25×. The number tells you the LLM is being conservative or the connection-article boundary is too high.
- **46 connection articles is the wrong question.** What matters is **inline `[[wikilink]]` count per concept article**. If a typical concept has only 2–3 wikilinks in its body, you're under-linking inline regardless of how many connection articles exist.
- **Run the orphan check.** Filter graph to `knowledge/concepts/`, count nodes with zero edges. If >5%, the compile prompt isn't integrating. If <2%, sparseness is structural not orphan-driven.

---

## 8. Prioritized Action List

1. **Pass-2 retro-link step in `compile.py`.** After every ingest, take the new concept and run a focused prompt over the last 30 existing concepts asking "should any of these link to the new article? If yes, edit them." Fixes append-only drift (Mode C) — biggest single source of sparseness in append-only systems.

2. **Rewrite the connection prompt with quota + non-obviousness test.** Replace "create connections when you find non-obvious relationships" with: "Each new concept must link to ≥5 existing concepts inline. Reject any connection a reader could infer from titles alone. For connection articles, only create if you can write 3 sentences of genuine synthesis that don't restate either concept." Few-shot with 3 good and 2 bad examples from the existing vault.

3. **Install Graph Analysis plugin and run Link Prediction.** Adamic-Adar produces a ranked list of concept pairs the topology says *should* be connected but aren't. Free oracle for prompt-tuning the compile step — feed the top 50 predictions back to the LLM and ask "are these real? add wikilinks where yes." Single biggest one-time graph quality jump.

4. **Build 4–6 MOCs from the highest-betweenness clusters.** Hand-write or AI-draft a `knowledge/mocs/<theme>.md` for each cluster (agent-architecture, agentic-foundation, claude-tooling…), plus one `_home.md` that links them. Color-group in graph view. Eliminates hub-domination (Mode A) by introducing intermediate bridge nodes.

5. **Typed-relation frontmatter + lint for markdown-link mistakes.** Emit `relations: [{type, target}]` in YAML. Add a lint rule that flags any `[text](path.md)` syntax pointing at vault files (Mode D — silent edge drop). Even before installing Graph Link Types, the typed metadata becomes Dataview-queryable for "show me all `contradicts` relations" — gives the graph the synthesis-grade semantics that untyped wikilinks lack.

---

## Sources

**Karpathy primary:**
- Karpathy gist 442a6bf — `https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f`
- Karpathy tweet — LLM Knowledge Bases — `https://x.com/karpathy/status/2039805659525644595`
- Karpathy tweet — Farzapedia follow-up — `https://x.com/karpathy/status/2040572272944324650`
- VentureBeat coverage — `https://venturebeat.com/data/karpathy-shares-llm-knowledge-base-architecture-that-bypasses-rag-with-an`

**Cole Medin / Claude Memory Compiler:**
- `https://github.com/coleam00/claude-memory-compiler`
- `https://github.com/coleam00/claude-memory-compiler/blob/main/AGENTS.md`
- `https://www.cognitionus.com/blog/claude-memory-compiler-guide`
- `https://www.linkedin.com/posts/cole-medin-727752184_karpathys-llm-knowledge-bases-post-went-activity-7447022234956861441-1RZV`
- `https://www.youtube.com/watch?v=7huCP6RkcY4`
- `https://www.mindstudio.ai/blog/self-evolving-claude-code-memory-obsidian-hooks`

**Critiques & v2 patterns:**
- LLM Wiki v2 (rohitg00) — `https://gist.github.com/rohitg00/2067ab416f7bbe447c1977edaaa681e2`
- ghelburlabs — `https://ghelburlabs.substack.com/p/i-rebuilt-karpathys-llm-wiki-heres`
- bitsofchris — `https://bitsofchris.com/p/an-llm-wiki-wont-compound-your-knowledge`
- aimaker.substack — `https://aimaker.substack.com/p/llm-wiki-obsidian-knowledge-base-andrej-karphaty`
- Hacker News thread — `https://news.ycombinator.com/item?id=47899844`
- dev.to — `https://dev.to/zaferdace/karpathys-obsidian-wiki-broke-at-100-articles-rag-fixed-it-4d4h`
- Louis Wang — `https://louiswang524.github.io/blog/llm-knowledge-base/`
- antigravity.codes — `https://antigravity.codes/blog/karpathy-llm-wiki-idea-file`

**PKM theory:**
- Andy Matuschak — Evergreen notes should be densely linked — `https://notes.andymatuschak.org/Evergreen_notes_should_be_densely_linked`
- Andy Matuschak — Evergreen notes should be atomic — `https://notes.andymatuschak.org/Evergreen_notes_should_be_atomic`
- Nick Milo — useful relationships between notes — `https://medium.com/@nickmilo22/in-what-ways-can-we-form-useful-relationships-between-notes-9b9ec46973c6`
- LYT Kit — MOCs Overview — `https://notes.linkingyourthinking.com/Cards/MOCs+Overview`
- dsebastien — `https://www.dsebastien.net/2022-05-15-maps-of-content/`
- Maggie Appleton — `https://maggieappleton.com/topics/digital-gardening/`

**Discourse graphs / typed links:**
- Joel Chan — `https://publish.obsidian.md/joelchan-notes/discourse-graph/patterns/PTN+-+discourse+graph`
- `https://discoursegraphs.com/`
- `https://github.com/DiscourseGraphs/discourse-graph-obsidian`
- Joel Chan paper — `https://joelchan.me/assets/pdf/Discourse_Graphs_for_Augmented_Knowledge_Synthesis_What_and_Why.pdf`
- thinkstack.club — `https://thinkstack.club/questions-claims-and-evidence-an-introduction-to-the-discourse-graph-extension-with-cortex-futura/`

**Obsidian graph & plugins:**
- Obsidian Help — Graph view — `https://help.obsidian.md/plugins/graph`
- Forum — What's the point of the graph view? — `https://forum.obsidian.md/t/whats-the-point-of-the-graph-view-how-are-you-using-it/71316`
- Forum — How should I use graph view "correctly"? — `https://forum.obsidian.md/t/q-how-should-i-use-graph-view-correctly-because-im-not-getting-any-ideas/82382`
- `https://github.com/SkepticMystic/graph-analysis`
- InfraNodus — `https://infranodus.com/obsidian-plugin`
- Nodus Labs — 3D graph view + network science — `https://noduslabs.com/featured/obsidian-3d-graph-view-plugin-with-network-science-insights/`
- `https://github.com/brianpetro/obsidian-smart-connections`
- Smart Connections homepage — `https://smartconnections.app/smart-connections/`
- XDA — Juggl — `https://www.xda-developers.com/obsidian-plugin-makes-graph-feature-less-overwhelming-useful/`
- obsidianstats — Graph Link Types — `https://www.obsidianstats.com/plugins/graph-link-types`
- `https://github.com/seqis/ObsidianMOC`
- MakeUseOf — orphan notes — `https://www.makeuseof.com/orphan-notes-in-obsidian-linking-system/`
