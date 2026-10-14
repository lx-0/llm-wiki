// Pure pass/fail rules of the screenshot harness — kept out of capture.cjs (which needs
// electron) so vitest can pin them.

/** The layout gate: strict pages fail on any overlap, off-screen or clipped text; the rest is
 *  audited and reported, never failed. */
function layoutFailures(strictPages, page, layout) {
  if (!strictPages.has(page)) return [];
  return [...layout.overlaps, ...layout.offscreen, ...layout.clipped];
}

/** The rest-height gate: a panel surface names the state that is its resting look and the
 *  height main will grant it; asking for more means the operator scrolls before reading. */
function restHeightFailure(surface, scheme, state, height) {
  const budget = surface.restHeight;
  if (!budget || state !== budget.state || height == null || height <= budget.max) return null;
  return `${surface.page}-${scheme}-${state} requests ${height} px at rest (max ${budget.max})`;
}

module.exports = { layoutFailures, restHeightFailure };
