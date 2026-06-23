// Atlas view — a hierarchical knowledge graph of connected node-cards, in the
// understand-anything style. Three layers (vault → knowledge types → entries) as
// rounded cards with a type-coloured accent + title, joined by edge-to-edge bezier
// connectors. Pan/zoom (zoom out = structure, zoom in = read), hover highlights the
// subtree, click an entry → Obsidian, click a type → focus.
import './index.css';

const TYPE_COLOR: Record<string, [number, number, number]> = {
  person: [224, 82, 176], project: [26, 184, 200], concept: [148, 132, 240],
  fact: [224, 86, 79], area: [52, 200, 110], map: [230, 180, 30], link: [240, 150, 70],
};
const NODE: [number, number, number] = [125, 211, 252];
const rgba = (c: [number, number, number], a: number) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;
const colorOf = (type: string): [number, number, number] => TYPE_COLOR[type] ?? NODE;
function esc(s: string): string {
  return s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c] as string);
}

type Entry = { title: string; file: string; type: string; mtimeMs: number };
type GNode = {
  id: string; kind: 'root' | 'type' | 'entry';
  label: string; type: string; file?: string;
  x: number; y: number; w: number; h: number; color: [number, number, number];
  parent?: GNode;
};

const canvas = document.getElementById('atlas-canvas') as HTMLCanvasElement;
const ctx = canvas.getContext('2d')!;
let W = 0, H = 0;
function resize(): void {
  const dpr = window.devicePixelRatio || 1;
  W = canvas.clientWidth || window.innerWidth;
  H = canvas.clientHeight || window.innerHeight;
  canvas.width = Math.round(W * dpr);
  canvas.height = Math.round(H * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}
window.addEventListener('resize', resize);

let nodes: GNode[] = [];
const edges: [GNode, GNode][] = [];
let vaultName = '';

const ENTRIES_PER_TYPE = 10;
const X_ROOT = -480, X_TYPE = -110, X_ENTRY = 250;
const H_ROOT = 36, H_TYPE = 30, H_ENTRY = 26;
const ROW = 12; // gap between stacked cards
const fontFor = (k: GNode['kind']) => (k === 'root' ? '700 14px' : k === 'type' ? '700 13px' : '500 11.5px');

function cardWidth(label: string, kind: GNode['kind']): number {
  ctx.font = `${fontFor(kind)} -apple-system, BlinkMacSystemFont, sans-serif`;
  const max = kind === 'entry' ? 210 : 168;
  return Math.min(max, ctx.measureText(label).width + 26);
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

  const root: GNode = { id: 'root', kind: 'root', label: vaultName || 'vault', type: 'root', x: X_ROOT, y: 0, w: cardWidth(vaultName || 'vault', 'root'), h: H_ROOT, color: NODE };
  nodes = [root];
  edges.length = 0;

  const blockH = (count: number) => Math.min(count, ENTRIES_PER_TYPE) * (H_ENTRY + ROW);
  let total = 0;
  for (const [, list] of types) total += Math.max(H_TYPE + ROW, blockH(list.length)) + 30;
  let cursor = -total / 2;

  types.forEach(([type, list]) => {
    const h = Math.max(H_TYPE + ROW, blockH(list.length));
    const cy = cursor + h / 2;
    cursor += h + 30;
    const tlabel = `${type} · ${list.length}`;
    const tn: GNode = { id: `t:${type}`, kind: 'type', label: tlabel, type, x: X_TYPE, y: cy, w: cardWidth(tlabel, 'type'), h: H_TYPE, color: colorOf(type), parent: root };
    nodes.push(tn);
    edges.push([root, tn]);

    const shown = list.slice(0, ENTRIES_PER_TYPE);
    shown.forEach((e, ei) => {
      const en: GNode = {
        id: `e:${e.file}`, kind: 'entry', label: e.title, type: e.type, file: e.file,
        x: X_ENTRY, y: cy + (ei - (shown.length - 1) / 2) * (H_ENTRY + ROW), w: cardWidth(e.title, 'entry'), h: H_ENTRY, color: colorOf(e.type), parent: tn,
      };
      nodes.push(en);
      edges.push([tn, en]);
    });
  });

  zoom = Math.max(0.55, Math.min(0.85, (H - 140) / Math.max(total, 1))); // readable cards by default; pan to explore
  panX = -((X_ROOT + X_ENTRY) / 2) * zoom;
  panY = 0;
}

// camera
let zoom = 0.6, panX = 0, panY = 0;
let reveal = 0;
let hover: GNode | null = null;
const toScreen = (x: number, y: number, rv: number) => ({ x: W / 2 + x * rv * zoom + panX, y: H / 2 + y * rv * zoom + panY });

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

function draw(now: number): void {
  reveal += (1 - reveal) * 0.05;
  const rv = reveal < 0.999 ? 1 - Math.pow(1 - reveal, 3) : 1;
  ctx.clearRect(0, 0, W, H);

  // edges — additive glow, edge-to-edge bezier
  ctx.globalCompositeOperation = 'lighter';
  for (const [a, b] of edges) {
    const sa = toScreen(a.x, a.y, rv), sb = toScreen(b.x, b.y, rv);
    const ax = sa.x + (a.w * zoom) / 2, bx = sb.x - (b.w * zoom) / 2;
    const hot = hover && (a === hover || b === hover || a === hover.parent || b === hover.parent);
    ctx.strokeStyle = rgba(b.color, hot ? 0.7 : b.kind === 'entry' ? 0.16 : 0.32);
    ctx.lineWidth = hot ? 1.7 : 1;
    const mx = (ax + bx) / 2;
    ctx.beginPath();
    ctx.moveTo(ax, sa.y);
    ctx.bezierCurveTo(mx, sa.y, mx, sb.y, bx, sb.y);
    ctx.stroke();
  }
  ctx.globalCompositeOperation = 'source-over';

  // node cards
  ctx.textBaseline = 'middle';
  for (const n of nodes) {
    const p = toScreen(n.x, n.y, rv);
    const w = n.w * zoom, h = n.h * zoom;
    const x = p.x - w / 2, y = p.y - h / 2;
    const isHover = n === hover;
    const subtle = hover && !isHover && hover.parent !== n && n.parent !== hover && n !== hover.parent;
    const alpha = subtle ? 0.45 : 1;
    // card body
    roundRect(x, y, w, h, 6 * zoom + 1);
    ctx.fillStyle = `rgba(13,21,40,${0.92 * alpha})`;
    if (isHover) {
      ctx.shadowColor = rgba(n.color, 0.8);
      ctx.shadowBlur = 18;
    }
    ctx.fill();
    ctx.shadowBlur = 0;
    ctx.strokeStyle = rgba(n.color, (isHover ? 0.95 : 0.5) * alpha);
    ctx.lineWidth = isHover ? 1.6 : 1;
    ctx.stroke();
    // type accent bar (left)
    roundRect(x, y, Math.max(3, 3.5 * zoom), h, 6 * zoom + 1);
    ctx.fillStyle = rgba(n.color, alpha);
    ctx.fill();
    // node dot
    ctx.beginPath();
    ctx.arc(x + 11 * zoom, p.y, 3 * zoom, 0, Math.PI * 2);
    ctx.fillStyle = rgba(n.color, alpha);
    ctx.shadowColor = rgba(n.color, 0.7);
    ctx.shadowBlur = 6;
    ctx.fill();
    ctx.shadowBlur = 0;
    // label (only when card is large enough to read)
    if (h > 13) {
      ctx.font = `${fontFor(n.kind)} -apple-system, BlinkMacSystemFont, sans-serif`;
      ctx.fillStyle = `rgba(${n.kind === 'entry' ? '210,222,240' : '236,242,250'},${(n.kind === 'entry' ? 0.85 : 1) * alpha})`;
      ctx.textAlign = 'left';
      const pad = 18 * zoom;
      const maxw = w - pad - 8 * zoom;
      let label = n.label;
      if (ctx.measureText(label).width > maxw) {
        while (label.length > 1 && ctx.measureText(label + '…').width > maxw) label = label.slice(0, -1);
        label += '…';
      }
      ctx.fillText(label, x + pad, p.y + 0.5);
    }
  }
  ctx.textAlign = 'start';

  requestAnimationFrame(draw);
}

// ── interaction ──
function nodeAt(px: number, py: number): GNode | null {
  for (let i = nodes.length - 1; i >= 0; i--) {
    const n = nodes[i];
    const p = toScreen(n.x, n.y, 1);
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
    const n = nodeAt(e.clientX, e.clientY);
    if (n?.kind === 'entry' && n.file) window.vault.openFile(n.file);
    else if (n?.kind === 'type') {
      panX = -(n.x * zoom);
      panY = -(n.y * zoom);
    }
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
    tip.innerHTML = `<span class="type-badge t-${n.type.replace(/[^a-z]/gi, '').toLowerCase() || 'note'}">${esc(n.type)}</span><span class="ck-tip-title">${esc(n.label)}</span>`;
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
  const nz = Math.max(0.2, Math.min(2.4, zoom * Math.exp(-e.deltaY * 0.0012)));
  const wx = (e.clientX - W / 2 - panX) / zoom;
  const wy = (e.clientY - H / 2 - panY) / zoom;
  zoom = nz;
  panX = e.clientX - W / 2 - wx * zoom;
  panY = e.clientY - H / 2 - wy * zoom;
}, { passive: false });

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
