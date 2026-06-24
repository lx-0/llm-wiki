// Single source for the knowledge-type colour palette (RGB), shared by the atlas +
// cockpit canvases. The `.t-*` classes in index.css mirror these exact values by hand
// (CSS can't import TS) — if you change one here, change the matching `.t-*` rule too.
export type RGB = [number, number, number];

export const TYPE_COLOR: Record<string, RGB> = {
  person: [224, 82, 176],
  project: [26, 184, 200],
  concept: [148, 132, 240],
  fact: [224, 86, 79],
  area: [52, 200, 110],
  map: [230, 180, 30],
  link: [240, 150, 70],
};

export const NODE: RGB = [125, 211, 252]; // default node (cyan)
export const GLOW: RGB = [167, 139, 250]; // ambient glow (violet)
