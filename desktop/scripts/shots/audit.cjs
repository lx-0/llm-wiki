// Page-side layout audit for the screenshot harness — the PNG gates from the repo's
// infographic rule (overlap, overflow) applied to the live DOM of every captured window.
//
// Runs inside the page via webContents.executeJavaScript and returns
//   { clipped: string[], overlaps: string[], offscreen: string[] }
// where each entry names the offending element(s) by tag + id/class + a text excerpt.
// Thresholds: text-on-text overlap > 100 px² fails; clipped text = scrollWidth exceeds
// clientWidth on an element that hides overflow or forbids wrapping; offscreen = any text leaf
// whose box ends past the viewport width.

const AUDIT_SCRIPT = `(() => {
  const describe = (el) => {
    const id = el.id ? '#' + el.id : '';
    const cls = el.classList.length ? '.' + [...el.classList].slice(0, 2).join('.') : '';
    const text = (el.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 40);
    return el.tagName.toLowerCase() + id + cls + (text ? ' "' + text + '"' : '');
  };
  const vw = document.documentElement.clientWidth;
  const vh = document.documentElement.clientHeight;
  const intersect = (a, b) => ({
    left: Math.max(a.left, b.left),
    top: Math.max(a.top, b.top),
    right: Math.min(a.right, b.right),
    bottom: Math.min(a.bottom, b.bottom),
  });
  const hasArea = (r) => r.right - r.left > 0 && r.bottom - r.top > 0;
  // The region in which an element can actually be seen: the viewport intersected with every
  // ancestor that clips its overflow (scroll containers, overflow:hidden) — rows scrolled past
  // the end of a list must not count as overlapping the footer they sit behind.
  const clipRect = (el) => {
    let clip = { left: 0, top: 0, right: vw, bottom: vh };
    for (let p = el.parentElement; p && p !== document.documentElement; p = p.parentElement) {
      const cs = getComputedStyle(p);
      if (/(hidden|auto|scroll|clip)/.test(cs.overflowX + cs.overflowY)) clip = intersect(clip, p.getBoundingClientRect());
    }
    return clip;
  };
  const visible = (el) => {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || Number(cs.opacity) === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && hasArea(intersect(r, clipRect(el)));
  };
  // text leaves: elements with a direct non-empty text node
  const leaves = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
  for (let el = walker.nextNode(); el; el = walker.nextNode()) {
    if (el.closest('[hidden]') || !visible(el)) continue;
    const ownText = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    if (ownText) leaves.push(el);
  }
  const clipped = [];
  const offscreen = [];
  for (const el of leaves) {
    const cs = getComputedStyle(el);
    const hides = cs.overflowX === 'hidden' || cs.overflow === 'hidden' || cs.whiteSpace === 'nowrap';
    if (hides && el.scrollWidth > el.clientWidth + 1 && cs.textOverflow !== 'ellipsis') clipped.push(describe(el));
    const r = el.getBoundingClientRect();
    if (r.right > vw + 1) offscreen.push(describe(el));
  }
  // Opaque layers (popovers, marked data-layer) hide whatever sits under them: text beneath a
  // layer is covered, not overlapped. Cut each leaf's boxes by every layer it is not part of.
  const layers = [...document.querySelectorAll('[data-layer]')].filter(visible).map((el) => ({ el, r: el.getBoundingClientRect() }));
  const subtract = (r, cut) => {
    const i = intersect(r, cut);
    if (!hasArea(i)) return [r];
    const out = [];
    if (i.top > r.top) out.push({ left: r.left, top: r.top, right: r.right, bottom: i.top });
    if (i.bottom < r.bottom) out.push({ left: r.left, top: i.bottom, right: r.right, bottom: r.bottom });
    if (i.left > r.left) out.push({ left: r.left, top: i.top, right: i.left, bottom: i.bottom });
    if (i.right < r.right) out.push({ left: i.right, top: i.top, right: r.right, bottom: i.bottom });
    return out;
  };
  const uncovered = (el, rs) =>
    layers.reduce((acc, layer) => (layer.el.contains(el) ? acc : acc.flatMap((r) => subtract(r, layer.r))), rs);
  // Per-line boxes (getClientRects), each cut to the element's visible region, so a wrapped
  // inline element is not one rectangle spanning both lines and a row scrolled out of its
  // list does not collide with what sits below the list.
  const overlaps = [];
  const boxes = leaves.map((el) => {
    const clip = clipRect(el);
    return { el, rs: uncovered(el, [...el.getClientRects()].map((r) => intersect(r, clip)).filter(hasArea)) };
  });
  const area = (a, b) => {
    const w = Math.min(a.right, b.right) - Math.max(a.left, b.left);
    const h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
    return w > 0 && h > 0 ? w * h : 0;
  };
  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) {
      const a = boxes[i], b = boxes[j];
      if (a.el.contains(b.el) || b.el.contains(a.el)) continue;
      let worst = 0;
      for (const ra of a.rs) for (const rb of b.rs) worst = Math.max(worst, area(ra, rb));
      if (worst > 100) overlaps.push(describe(a.el) + ' <> ' + describe(b.el) + ' (' + Math.round(worst) + ' px²)');
    }
  }
  return { clipped, overlaps, offscreen };
})()`;

module.exports = { AUDIT_SCRIPT };
