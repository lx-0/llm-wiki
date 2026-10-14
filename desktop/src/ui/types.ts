// Entity-type token lookup shared by badges, dots and rows: the CSS custom property for a
// kind, with unknown kinds falling back to `note` so a new engine folder never renders unstyled.

const KNOWN = new Set(['person', 'project', 'concept', 'fact', 'area', 'map', 'link', 'note']);

/** `--type-<kind>` for a known kind, `--type-note` otherwise. */
export function typeToken(kind: string): string {
  const slug = kind.replace(/[^a-z]/gi, '').toLowerCase();
  return `--type-${KNOWN.has(slug) ? slug : 'note'}`;
}
