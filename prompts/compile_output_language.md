## Output language

Always write **all prose** — article titles, body text, summaries, list items, and narrative — in **${output_language}**, regardless of the source material's language (English meetings, English articles, mixed-language transcripts all become ${output_language} prose). Translate the meaning into ${output_language}; never mix two languages inside a sentence. **This directive overrides any earlier instruction about matching the source material's language.**

Keep the following **verbatim** — never translate them, regardless of the target language:

- code, code comments, file paths, shell commands, and technical identifiers;
- proper names of products, companies, tools, and people;
- the canonical structural section headers — `## State`, `## Action Items`, `## Open Threads`, `## Timeline`, `## Key Points`, `## Summary`, `## Transcript`, and the like. These are parsed downstream by sentinel-managed blocks and dedup; translating a header silently breaks the pipeline.
