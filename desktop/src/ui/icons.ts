// One icon set, one stroke width. Inline SVG strings (24-grid, 1.75 stroke, round caps) so
// components can drop them into markup via {@html}; colour comes from `currentColor`.

const wrap = (body: string, size = 16): string =>
  `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;

export const icon = {
  logo: (size = 16) =>
    wrap(
      '<path d="M11 4.4c-1.4-.8-3.4-.3-4 1.2-1.5.1-2.6 1.3-2.6 2.8 0 .3 0 .6.1.9-1 .5-1.6 1.5-1.6 2.6 0 .9.4 1.7 1.1 2.2-.2.4-.3.8-.3 1.3 0 1.5 1.2 2.7 2.8 2.8.5.9 1.5 1.5 2.6 1.5h1.8V4.9"/><path d="M13 4.4c1.4-.8 3.4-.3 4 1.2 1.5.1 2.6 1.3 2.6 2.8 0 .3 0 .6-.1.9 1 .5 1.6 1.5 1.6 2.6 0 .9-.4 1.7-1.1 2.2.2.4.3.8.3 1.3 0 1.5-1.2 2.7-2.8 2.8-.5.9-1.5 1.5-2.6 1.5h-1.8V4.9"/>',
      size,
    ),
  search: (size = 16) => wrap('<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>', size),
  inbox: (size = 16) =>
    wrap(
      '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
      size,
    ),
  settings: (size = 16) =>
    wrap(
      '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 0 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 0 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 0 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 0 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
      size,
    ),
  overview: (size = 16) =>
    wrap(
      '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
      size,
    ),
  notes: (size = 16) =>
    wrap('<path d="M4 4h12l4 4v12H4z"/><path d="M16 4v4h4"/><path d="M8 13h8M8 17h5"/>', size),
  chevron: (size = 16) => wrap('<path d="m9 6 6 6-6 6"/>', size),
  copy: (size = 16) =>
    wrap(
      '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
      size,
    ),
  check: (size = 16) => wrap('<path d="M20 6 9 17l-5-5"/>', size),
  close: (size = 16) => wrap('<path d="M18 6 6 18M6 6l12 12"/>', size),
  external: (size = 16) =>
    wrap(
      '<path d="M14 4h6v6"/><path d="M20 4 10 14"/><path d="M20 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h5"/>',
      size,
    ),
  plus: (size = 16) => wrap('<path d="M12 5v14M5 12h14"/>', size),
  play: (size = 16) => wrap('<path d="M7 5v14l11-7z"/>', size),
  pause: (size = 16) => wrap('<path d="M8 5v14M16 5v14"/>', size),
  refresh: (size = 16) => wrap('<path d="M21 12a9 9 0 1 1-2.6-6.4"/><path d="M21 4v5h-5"/>', size),
} as const;

export type IconName = keyof typeof icon;
