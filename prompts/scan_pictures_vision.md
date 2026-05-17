Analyze this photograph. This is a camera / phone photo (not a screen capture). Your analysis will be stored alongside the image for search, and a knowledge compiler will use it to decide whether the photo is worth indexing.

Respond with ONLY a JSON object (no markdown, no code fences):

{
  "scene_description": "<what the photo shows, 1-2 sentences, concrete>",
  "setting": "<short location/context cue, e.g. 'indoor workshop', 'kitchen counter', 'city street at dusk', 'whiteboard in office'. null if unclear>",
  "objects": ["object1", "object2", "object3"],
  "action": "<what is happening, 1 sentence. null if static scene with no activity>",
  "text_visible": "<verbatim text legible in the photo — whiteboard scribbles, receipts, signage, screen content, packaging. Max 500 chars. null if no readable text>",
  "people_present": <true|false>,
  "tags": ["tag1", "tag2", "tag3"],
  "relevance": "<keep|ephemeral>"
}

Rules:
- scene_description: imagine the operator searching for this photo in 6 months — what would they remember? Describe content, not interpretation.
- setting: lightweight location/context hint. "indoor", "outdoor" alone is not enough — add the WHAT ("kitchen", "workshop", "park trail").
- objects: 3-7 concrete nouns visible in frame. Lowercase, singular. Skip background filler.
- action: short verb-phrase if something is happening ("hands assembling a model", "person writing on whiteboard"). null for pure-still scenes.
- text_visible: VERBATIM text. Whiteboards, receipts, document scans, packaging labels, screen reflections — anything legible. This is the strongest "keep" signal for photos.
- people_present: true if any humans (incl. hands, faces, silhouettes) are in frame.
- tags: 3-5 lowercase. Mix domain ("woodworking", "cooking", "meeting") with object/scene class ("whiteboard", "receipt", "diagram").
- relevance:
    "keep" — contains text worth preserving (whiteboard, receipt, doc scan, signage with names/dates), captures a project / build / artifact, or documents a non-trivial scene the operator might revisit.
    "ephemeral" — casual snapshot, food photo without recipe text, blurry / decorative / aesthetic, transient action with no durable signal.
- Respond with ONLY the JSON object, nothing else.
