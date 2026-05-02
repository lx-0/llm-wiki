Analyze this screenshot. Your analysis will be stored as metadata alongside the image for search and retrieval. A knowledge compiler will use it to understand the user's work context and projects.

Respond with ONLY a JSON object (no markdown, no code fences):

{
  "app": "<specific application name, e.g. VS Code, Firefox, Obsidian, Slack, Terminal>",
  "project": "<project or product name if recognizable, e.g. ${project_examples_inline}, null if unclear>",
  "summary": "<what this screenshot shows, 1-2 sentences, focus on WHAT and WHY>",
  "key_text": "<important visible text: headings, error messages, code snippets, URLs. Max 300 chars. Skip UI chrome.>",
  "tags": ["tag1", "tag2", "tag3"],
  "relevance": "<keep|ephemeral>"
}

Rules:
- app: be specific (not "browser" but "Firefox", not "editor" but "VS Code")
- project: look for repo names, product names, domain names, logos. null if generic/personal
- summary: imagine someone searching for this screenshot in 6 months. What would they search for?
- key_text: extract text that carries MEANING — error messages, function names, config values, URLs, headings
- tags: 3-5 lowercase tags, mix of broad (coding, email, config) and specific (kubernetes, typescript, project-name)
- relevance: "keep" = contains useful information (errors, configs, decisions, results). "ephemeral" = transient UI state, notifications, nothing worth indexing
- Respond with ONLY the JSON object, nothing else
