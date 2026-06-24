// Atlas view — a hierarchical knowledge graph of connected node-cards (understand-
// anything style), heavily pimped: glass cards with type glow, gradient edges with
// flowing data pulses, a blueprint grid + starfield + nebula backdrop, a staggered
// entrance, and hover that lights the whole path to the root. Pan/zoom, click an
// entry → Obsidian, a type → focus.
import './index.css';
import { TYPE_COLOR, NODE, GLOW } from './lib/types';

const rgba = (c: [number, number, number], a: number) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;
const colorOf = (t: string): [number, number, number] => TYPE_COLOR[t] ?? NODE;
function esc(s: string): string {
  return s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c] as string);
}
function fmtAgo(ms: number): string {
  const s = Math.max(0, (Date.now() - ms) / 1000);
  if (s < 90) return 'now';
  const m = s / 60;
  if (m < 90) return `${Math.round(m)}m ago`;
  const h = m / 60;
  if (h < 36) return `${Math.round(h)}h ago`;
  return `${Math.round(h / 24)}d ago`;
}

type Entry = { title: string; file: string; type: string; mtimeMs: number };
type GNode = {
  id: string; kind: 'root' | 'type' | 'entry'; label: string; sub: string; type: string; file?: string;
  x: number; y: number; w: number; h: number; color: [number, number, number]; parent?: GNode; mtime?: number; weight?: number;
};
let maxWeight = 1; // largest type's entry count — for centrality-scaled node dots

const canvas = document.getElementById('atlas-canvas') as HTMLCanvasElement;
const ctx = canvas.getContext('2d')!;
let W = 0, H = 0;
let stars: { x: number; y: number; a: number; tw: number }[] = [];
function resize(): void {
  const dpr = window.devicePixelRatio || 1;
  W = canvas.clientWidth || window.innerWidth;
  H = canvas.clientHeight || window.innerHeight;
  canvas.width = Math.round(W * dpr);
  canvas.height = Math.round(H * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  stars = Array.from({ length: 80 }, () => ({ x: Math.random() * W, y: Math.random() * H, a: 0.05 + Math.random() * 0.2, tw: Math.random() * 6.28 }));
}
window.addEventListener('resize', resize);

let nodes: GNode[] = [];
const edges: [GNode, GNode][] = [];
let vaultName = '';

const ENTRIES_PER_TYPE = 7;
const X_ROOT = -520, X_TYPE = -150, X_ENTRY = 250;
const H_ROOT = 48, H_TYPE = 44, H_ENTRY = 44, ROW = 14;
const fontFor = (k: GNode['kind']) => (k === 'root' ? '700 14.5px' : k === 'type' ? '700 13.5px' : '600 12px');
function cardWidth(label: string, kind: GNode['kind']): number {
  ctx.font = `${fontFor(kind)} -apple-system, BlinkMacSystemFont, sans-serif`;
  return Math.max(kind === 'entry' ? 150 : 130, Math.min(kind === 'entry' ? 232 : 190, ctx.measureText(label).width + 50));
}

async function build(): Promise<void> {
  const v = await window.vault.status();
  vaultName = v?.name ?? '';
  const entries = (await window.vault.list()) as Entry[];
  const byType = new Map<string, Entry[]>();
  for (const e of entries) {
    const a = byType.get(e.type) ?? [];
    a.push(e);
    byType.set(e.type, a);
  }
  const types = [...byType.entries()].sort((a, b) => b[1].length - a[1].length);
  maxWeight = Math.max(1, ...types.map(([, l]) => l.length));

  const root: GNode = { id: 'root', kind: 'root', label: vaultName || 'vault', sub: `${(v?.articleCount ?? 0).toLocaleString()} notes`, type: 'root', x: X_ROOT, y: 0, w: cardWidth(vaultName || 'vault', 'root'), h: H_ROOT, color: NODE };
  nodes = [root];
  edges.length = 0;

  const blockH = (c: number) => Math.min(c, ENTRIES_PER_TYPE) * (H_ENTRY + ROW);
  let total = 0;
  for (const [, list] of types) total += Math.max(H_TYPE + ROW, blockH(list.length)) + 32;
  let cursor = -total / 2;
  types.forEach(([type, list]) => {
    const h = Math.max(H_TYPE + ROW, blockH(list.length));
    const cy = cursor + h / 2;
    cursor += h + 32;
    const wf = list.length / maxWeight; // 0..1 — heavier types become bigger cards (gravity)
    const tn: GNode = { id: `t:${type}`, kind: 'type', label: type, sub: `${list.length} ${list.length === 1 ? 'entry' : 'entries'}`, type, x: X_TYPE, y: cy, w: cardWidth(type, 'type') * (1 + 0.32 * wf), h: H_TYPE * (1 + 0.42 * wf), color: colorOf(type), parent: root, weight: list.length };
    nodes.push(tn);
    edges.push([root, tn]);
    list.slice(0, ENTRIES_PER_TYPE).forEach((e, ei, arr) => {
      const en: GNode = {
        id: `e:${e.file}`, kind: 'entry', label: e.title, sub: fmtAgo(e.mtimeMs), type: e.type, file: e.file, mtime: e.mtimeMs,
        x: X_ENTRY, y: cy + (ei - (arr.length - 1) / 2) * (H_ENTRY + ROW), w: cardWidth(e.title, 'entry'), h: H_ENTRY, color: colorOf(e.type), parent: tn,
      };
      nodes.push(en);
      edges.push([tn, en]);
    });
  });

  zoom = Math.max(0.62, Math.min(0.85, (H - 140) / Math.max(total, 1)));
  panX = -((X_ROOT + X_ENTRY) / 2) * zoom;
  panY = 0;
  const tel = document.getElementById('atlas-telemetry');
  if (tel) tel.innerHTML = `<span>${nodes.length} NODES</span><span class="ck-tel-sep">//</span><span>${types.length} LAYERS</span><span class="ck-tel-sep">//</span><span>${edges.length} LINKS</span>`;
}

// camera
let zoom = 0.6, panX = 0, panY = 0;
let reveal = 0;
let hover: GNode | null = null;
let expandedNode: GNode | null = null; // entry whose card is expanded in place
const toScreen = (x: number, y: number) => ({ x: W / 2 + x * zoom + panX, y: H / 2 + y * zoom + panY });

function roundRect(x: number, y: number, w: number, h: number, r: number): void {
  r = Math.min(r, h / 2, w / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}
const ease = (r: number) => 1 - Math.pow(1 - Math.max(0, Math.min(1, r)), 3);
function ellipsize(s: string, maxw: number): string {
  if (ctx.measureText(s).width <= maxw) return s;
  let t = s;
  while (t.length > 1 && ctx.measureText(t + '…').width > maxw) t = t.slice(0, -1);
  return t + '…';
}
function wrapText(s: string, maxw: number, maxLines: number): string[] {
  const words = s.replace(/\s+/g, ' ').trim().split(' ');
  const lines: string[] = [];
  let cur = '';
  for (const w of words) {
    const test = cur ? `${cur} ${w}` : w;
    if (ctx.measureText(test).width > maxw && cur) {
      lines.push(cur);
      cur = w;
      if (lines.length >= maxLines) {
        lines[maxLines - 1] = ellipsize(lines[maxLines - 1] + '…', maxw);
        return lines;
      }
    } else cur = test;
  }
  if (cur && lines.length < maxLines) lines.push(cur);
  return lines;
}
function nodeReveal(n: GNode): number {
  const delay = n.kind === 'root' ? 0 : n.kind === 'type' ? 0.12 : 0.26;
  return ease((reveal - delay) / 0.4);
}
function activeSet(focus: GNode | null): Set<GNode> | null {
  if (!focus) return null;
  const s = new Set<GNode>();
  let n: GNode | undefined = focus;
  while (n) {
    s.add(n);
    n = n.parent;
  }
  for (const m of nodes) if (m.parent === focus) s.add(m);
  return s;
}

function draw(now: number): void {
  reveal = Math.min(1.4, reveal + 0.012);
  const t = now / 1000;
  const active = activeSet(hover || expandedNode);
  ctx.clearRect(0, 0, W, H);

  // ── backdrop: blueprint grid (screen) + nebula + starfield ──
  ctx.globalCompositeOperation = 'lighter';
  const neb = ctx.createRadialGradient(W * 0.5, H * 0.45, 0, W * 0.5, H * 0.45, Math.max(W, H) * 0.6);
  neb.addColorStop(0, rgba(GLOW, 0.06));
  neb.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = neb;
  ctx.fillRect(0, 0, W, H);
  for (const s of stars) {
    const tw = 0.5 + 0.5 * Math.sin(t * 1.4 + s.tw);
    ctx.fillStyle = rgba([200, 220, 255], s.a * tw);
    ctx.fillRect(s.x, s.y, 1.2, 1.2);
  }
  ctx.globalCompositeOperation = 'source-over';
  ctx.strokeStyle = 'rgba(125,211,252,0.035)';
  ctx.lineWidth = 1;
  const gs = 46;
  for (let x = (panX % gs + gs) % gs; x < W; x += gs) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, H);
    ctx.stroke();
  }
  for (let y = (panY % gs + gs) % gs; y < H; y += gs) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(W, y);
    ctx.stroke();
  }

  // ── edges: gradient bezier + flowing data pulse ──
  ctx.globalCompositeOperation = 'lighter';
  for (const [a, b] of edges) {
    const rvB = nodeReveal(b);
    if (rvB <= 0.01) continue;
    const sa = toScreen(a.x, a.y), sb = toScreen(b.x, b.y);
    const ax = sa.x + (a.w * zoom) / 2, bx = sb.x - (b.w * zoom) / 2;
    const hot = active ? active.has(a) && active.has(b) : false;
    const dim = active && !hot ? 0.25 : 1;
    const g = ctx.createLinearGradient(ax, sa.y, bx, sb.y);
    g.addColorStop(0, rgba(a.color, (hot ? 0.7 : b.kind === 'entry' ? 0.18 : 0.32) * dim * rvB));
    g.addColorStop(1, rgba(b.color, (hot ? 0.7 : b.kind === 'entry' ? 0.18 : 0.32) * dim * rvB));
    ctx.strokeStyle = g;
    ctx.lineWidth = hot ? 1.8 : 1;
    const mx = (ax + bx) / 2;
    ctx.beginPath();
    ctx.moveTo(ax, sa.y);
    ctx.bezierCurveTo(mx, sa.y, mx, sb.y, bx, sb.y);
    ctx.stroke();
    // flowing data pulse along the edge
    if (rvB > 0.6) {
      const f = ((t * 0.35 + (a.y + b.y) * 0.002) % 1);
      const u = 1 - f;
      const px = u * u * u * ax + 3 * u * u * f * mx + 3 * u * f * f * mx + f * f * f * bx;
      const py = u * u * u * sa.y + 3 * u * u * f * sa.y + 3 * u * f * f * sb.y + f * f * f * sb.y;
      ctx.beginPath();
      ctx.arc(px, py, hot ? 2.4 : 1.6, 0, Math.PI * 2);
      ctx.fillStyle = rgba(b.color, (hot ? 0.95 : 0.5) * dim);
      ctx.shadowColor = rgba(b.color, 0.9);
      ctx.shadowBlur = hot ? 10 : 5;
      ctx.fill();
      ctx.shadowBlur = 0;
    }
  }
  ctx.globalCompositeOperation = 'source-over';

  // ── node cards ──
  ctx.textBaseline = 'middle';
  for (const n of nodes) {
    const nr = nodeReveal(n);
    if (nr <= 0.01) continue;
    if (n === expandedNode) continue; // rendered separately as the grown card
    const isHover = n === hover;
    const dim = active && !active.has(n) ? 0.32 : 1;
    const sc = (0.6 + 0.4 * nr) * (isHover ? 1.07 : 1);
    const p = toScreen(n.x, n.y);
    const w = n.w * zoom * sc, h = n.h * zoom * sc;
    const x = p.x - w / 2, y = p.y - h / 2;
    const a = nr * dim;
    const rad = 6 * zoom + 1;

    // soft glow halo around the card (type-coloured)
    roundRect(x, y, w, h, rad);
    ctx.shadowColor = rgba(n.color, (isHover ? 0.85 : 0.4) * a);
    ctx.shadowBlur = (isHover ? 22 : 9) * zoom;
    // glass body (vertical gradient)
    const gb = ctx.createLinearGradient(0, y, 0, y + h);
    gb.addColorStop(0, `rgba(22,33,57,${0.94 * a})`);
    gb.addColorStop(1, `rgba(11,18,34,${0.94 * a})`);
    ctx.fillStyle = gb;
    ctx.fill();
    ctx.shadowBlur = 0;
    // top inner highlight
    ctx.strokeStyle = `rgba(255,255,255,${0.05 * a})`;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x + rad, y + 0.5);
    ctx.lineTo(x + w - rad, y + 0.5);
    ctx.stroke();
    // border
    ctx.strokeStyle = rgba(n.color, (isHover ? 0.95 : 0.55) * a);
    ctx.lineWidth = isHover ? 1.6 : 1;
    roundRect(x, y, w, h, rad);
    ctx.stroke();
    // left accent bar
    roundRect(x, y, Math.max(3, 3.5 * zoom), h, rad);
    ctx.fillStyle = rgba(n.color, a);
    ctx.fill();
    // node dot — type cards' dots scale with their weight (entry count) so heavier
    // clusters read as gravity wells; the eye is pulled to what's load-bearing
    const wf = n.kind === 'type' ? (n.weight ?? 0) / maxWeight : 0;
    const dotR = (3 + wf * 4.5) * zoom * sc;
    ctx.beginPath();
    ctx.arc(x + 13 * zoom, p.y, dotR, 0, Math.PI * 2);
    ctx.fillStyle = rgba(n.color, a);
    ctx.shadowColor = rgba(n.color, 0.85);
    ctx.shadowBlur = 6 + wf * 10;
    ctx.fill();
    ctx.shadowBlur = 0;
    // labels: title + sub (box scales with zoom, text stays readable)
    const pad = 22 * zoom;
    const maxw = w - pad - 9 * zoom;
    ctx.textAlign = 'left';
    if (n.kind === 'type' && h > 22) {
      // type name as a filled-pill badge — the same token Browse/Panel/Recent use
      const label = n.label.toUpperCase();
      ctx.font = '700 9px -apple-system, BlinkMacSystemFont, sans-serif';
      const pw = Math.min(ctx.measureText(label).width + 13, maxw);
      const px = x + pad, py = p.y - 15;
      roundRect(px, py, pw, 15, 4);
      ctx.fillStyle = rgba(n.color, 0.2 * a);
      ctx.fill();
      ctx.fillStyle = rgba(n.color, a);
      ctx.fillText(ellipsize(label, pw - 9), px + 6, py + 8);
      ctx.font = '500 9.5px -apple-system, BlinkMacSystemFont, sans-serif';
      ctx.fillStyle = `rgba(170,185,205,${0.9 * a})`;
      ctx.fillText(ellipsize(n.sub, maxw), x + pad, p.y + 11);
    } else if (h > 26) {
      ctx.font = `${fontFor(n.kind)} -apple-system, BlinkMacSystemFont, sans-serif`;
      ctx.fillStyle = `rgba(238,244,252,${a})`;
      ctx.fillText(ellipsize(n.label, maxw), x + pad, p.y - 6);
      ctx.font = '500 9.5px -apple-system, BlinkMacSystemFont, sans-serif';
      ctx.fillStyle = rgba(n.color, 0.85 * a);
      ctx.fillText(ellipsize(n.sub, maxw), x + pad, p.y + 9);
    } else if (h > 13) {
      ctx.font = `${fontFor(n.kind)} -apple-system, BlinkMacSystemFont, sans-serif`;
      ctx.fillStyle = `rgba(238,244,252,${a})`;
      ctx.fillText(ellipsize(n.label, maxw), x + pad, p.y + 0.5);
    }
  }
  ctx.textAlign = 'start';

  // ── HUD corner brackets ──
  ctx.globalCompositeOperation = 'lighter';
  ctx.strokeStyle = rgba(NODE, 0.26);
  ctx.lineWidth = 1.5;
  const bm = 24, bl = 20;
  for (const [bx, by, sx, sy] of [[bm, bm, 1, 1], [W - bm, bm, -1, 1], [bm, H - bm, 1, -1], [W - bm, H - bm, -1, -1]] as const) {
    ctx.beginPath();
    ctx.moveTo(bx, by + sy * bl);
    ctx.lineTo(bx, by);
    ctx.lineTo(bx + sx * bl, by);
    ctx.stroke();
  }
  ctx.globalCompositeOperation = 'source-over';

  renderExpandedNode(); // the clicked node's own card, grown in place into a full card
  requestAnimationFrame(draw);
}

// ── interaction ──
function nodeAt(px: number, py: number): GNode | null {
  for (let i = nodes.length - 1; i >= 0; i--) {
    const n = nodes[i];
    const p = toScreen(n.x, n.y);
    const w = n.w * zoom, h = n.h * zoom;
    if (px >= p.x - w / 2 && px <= p.x + w / 2 && py >= p.y - h / 2 && py <= p.y + h / 2) return n;
  }
  return null;
}
let dragging = false, lastX = 0, lastY = 0, downX = 0, downY = 0;
const tip = document.getElementById('atlas-tip');
canvas.addEventListener('mousedown', (e) => {
  dragging = true;
  downX = lastX = e.clientX;
  downY = lastY = e.clientY;
});
window.addEventListener('mouseup', (e) => {
  if (!dragging) return;
  dragging = false;
  if (Math.hypot(e.clientX - downX, e.clientY - downY) < 5) {
    // clicks inside the grown card: footer strip → open, anything else (incl ×) → close
    if (expandedNode && expandT > 0.4) {
      const r = expRect;
      if (e.clientX >= r.x && e.clientX <= r.x + r.w && e.clientY >= r.y && e.clientY <= r.y + r.h) {
        if (e.clientY > r.y + r.h - 26 && expandedNode.file) window.vault.openFile(expandedNode.file);
        else collapse();
        return;
      }
    }
    const n = nodeAt(e.clientX, e.clientY);
    if (n?.kind === 'entry') expandEntry(n);
    else if (n?.kind === 'type') {
      panX = -(n.x * zoom);
      panY = -(n.y * zoom);
    } else collapse();
  }
});
canvas.addEventListener('mousemove', (e) => {
  if (dragging) {
    panX += e.clientX - lastX;
    panY += e.clientY - lastY;
    lastX = e.clientX;
    lastY = e.clientY;
  }
  const n = nodeAt(e.clientX, e.clientY);
  hover = n;
  canvas.style.cursor = dragging ? 'grabbing' : n ? 'pointer' : 'grab';
  if (!tip) return;
  if (n && n.kind !== 'root') {
    const sub = n.kind === 'entry' && n.mtime ? ` · ${fmtAgo(n.mtime)}` : '';
    tip.innerHTML = `<span class="type-badge t-${n.type.replace(/[^a-z]/gi, '').toLowerCase() || 'note'}">${esc(n.type)}</span><span class="ck-tip-title">${esc(n.label)}${sub}</span>`;
    tip.style.left = `${Math.min(e.clientX + 14, W - 290)}px`;
    tip.style.top = `${e.clientY + 14}px`;
    tip.classList.add('show');
  } else {
    tip.classList.remove('show');
  }
});
canvas.addEventListener('mouseleave', () => {
  hover = null;
  tip?.classList.remove('show');
});
canvas.addEventListener('wheel', (e) => {
  e.preventDefault();
  const nz = Math.max(0.2, Math.min(2.6, zoom * Math.exp(-e.deltaY * 0.0012)));
  const wx = (e.clientX - W / 2 - panX) / zoom;
  const wy = (e.clientY - H / 2 - panY) / zoom;
  zoom = nz;
  panX = e.clientX - W / 2 - wx * zoom;
  panY = e.clientY - H / 2 - wy * zoom;
}, { passive: false });

// ── expand a node-card IN PLACE on the canvas: click an entry → its card grows
//    into a full card with a lazily-loaded content preview; click it → Obsidian ──
let expandedText: string | null = null; // null = loading
let expandT = 0;
let expandedLines: string[] = [];
const EXP_W = 332;
function cleanMd(s: string): string {
  return s
    .replace(/```[\s\S]*?```/g, '')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\[\[([^\]]+)\]\]/g, (_m, p: string) => p.split('|')[0].split('#')[0].split('/').pop() || p)
    .replace(/^#{1,6}\s*/gm, '')
    .replace(/^>\s?/gm, '')
    .replace(/^[-*]\s/gm, '• ')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}
function collapse(): void {
  expandedNode = null;
  expandedText = null;
}
let expRect = { x: 0, y: 0, w: 0, h: 0 };
let expTargetH = H_ENTRY;
function computeLayout(): void {
  ctx.font = '400 12.5px -apple-system, BlinkMacSystemFont, sans-serif';
  expandedLines = expandedText === null ? ['Loading…'] : wrapText(expandedText, EXP_W - 32, 11);
  expTargetH = 60 + expandedLines.length * 17 + 28;
}
function expandEntry(n: GNode): void {
  if (!n.file) return;
  if (expandedNode === n) {
    collapse();
    return;
  } // toggle
  expandedNode = n;
  expandedText = null;
  expandT = 0;
  computeLayout();
  const file = n.file;
  void window.vault.preview(file).then((tx) => {
    if (expandedNode?.file === file) {
      expandedText = cleanMd(tx) || '(no content)';
      computeLayout();
    }
  });
}
// The clicked node's OWN card grows in place (centered on the node), morphing into
// the full detail card — not a separate overlay.
function renderExpandedNode(): void {
  if (!expandedNode) return;
  expandT += (1 - expandT) * 0.18;
  const n = expandedNode;
  const e = ease(expandT);
  const p = toScreen(n.x, n.y);
  const baseW = n.w * zoom, baseH = n.h * zoom;
  const w = baseW + (EXP_W - baseW) * e;
  const h = baseH + (expTargetH - baseH) * e;
  const x = p.x - w / 2, y = p.y - h / 2; // centered on the node → grows in place
  expRect = { x, y, w, h };
  // card body
  roundRect(x, y, w, h, 10);
  ctx.shadowColor = rgba(n.color, 0.5);
  ctx.shadowBlur = 14 + 22 * e;
  const gb = ctx.createLinearGradient(0, y, 0, y + h);
  gb.addColorStop(0, 'rgba(22,33,57,0.98)');
  gb.addColorStop(1, 'rgba(11,18,34,0.98)');
  ctx.fillStyle = gb;
  ctx.fill();
  ctx.shadowBlur = 0;
  roundRect(x, y, 3.5, h, 10);
  ctx.fillStyle = rgba(n.color, 1);
  ctx.fill();
  roundRect(x, y, w, h, 10);
  ctx.strokeStyle = rgba(n.color, 0.7);
  ctx.lineWidth = 1.2;
  ctx.stroke();
  ctx.textAlign = 'left';
  ctx.textBaseline = 'middle';
  // compact label (title + sub) — fades out as the full content fades in
  const ca = 1 - Math.min(1, e * 1.7);
  if (ca > 0.02) {
    ctx.globalAlpha = ca;
    ctx.font = `${fontFor(n.kind)} -apple-system, BlinkMacSystemFont, sans-serif`;
    ctx.fillStyle = '#eef4fc';
    ctx.fillText(ellipsize(n.label, w - 30), x + 18, p.y - 6);
    ctx.font = '500 9.5px -apple-system, BlinkMacSystemFont, sans-serif';
    ctx.fillStyle = rgba(n.color, 0.85);
    ctx.fillText(n.sub, x + 18, p.y + 9);
    ctx.globalAlpha = 1;
  }
  // full content — fades in once the card is mostly grown
  const fa = Math.max(0, Math.min(1, (e - 0.55) / 0.45));
  if (fa > 0.02) {
    ctx.globalAlpha = fa;
    ctx.font = '700 9px ui-monospace, monospace';
    const chip = n.type.toUpperCase();
    const chipW = ctx.measureText(chip).width + 14;
    roundRect(x + 16, y + 14, chipW, 16, 4);
    ctx.fillStyle = rgba(n.color, 0.2);
    ctx.fill();
    ctx.fillStyle = rgba(n.color, 1);
    ctx.fillText(chip, x + 23, y + 22.5);
    // close ×
    ctx.font = '400 17px -apple-system, sans-serif';
    ctx.fillStyle = 'rgba(226,232,240,0.6)';
    ctx.textAlign = 'center';
    ctx.fillText('×', x + w - 16, y + 21);
    ctx.textAlign = 'left';
    // title
    ctx.font = '700 14px -apple-system, BlinkMacSystemFont, sans-serif';
    ctx.fillStyle = '#eef4fc';
    ctx.fillText(ellipsize(n.label, w - 54), x + 16, y + 44);
    ctx.strokeStyle = rgba(n.color, 0.22);
    ctx.beginPath();
    ctx.moveTo(x + 16, y + 56);
    ctx.lineTo(x + w - 16, y + 56);
    ctx.stroke();
    ctx.font = '400 12.5px -apple-system, BlinkMacSystemFont, sans-serif';
    ctx.fillStyle = 'rgba(214,226,244,0.82)';
    expandedLines.forEach((ln, i) => ctx.fillText(ln, x + 16, y + 56 + 16 + i * 17));
    ctx.font = '600 9.5px ui-monospace, monospace';
    ctx.fillStyle = rgba(n.color, 0.75);
    ctx.fillText('OPEN IN OBSIDIAN ↗', x + 16, y + h - 13);
    ctx.globalAlpha = 1;
  }
  ctx.textBaseline = 'alphabetic';
}
window.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') collapse();
});

function renderLegend(): void {
  const el = document.getElementById('atlas-legend');
  if (!el) return;
  const types = [...new Set(nodes.filter((n) => n.kind === 'type').map((n) => n.type))];
  el.innerHTML = types
    .map((ty) => `<span class="atlas-leg"><span class="atlas-dot" style="background:${rgba(colorOf(ty), 1)}"></span>${esc(ty)}</span>`)
    .join('');
}

// ── wire up ──
resize();
void build().then(() => {
  renderLegend();
  const ve = document.getElementById('atlas-vault');
  if (ve) ve.textContent = vaultName;
});
requestAnimationFrame(draw);
document.getElementById('atlas-compact')?.addEventListener('click', () => window.close());
