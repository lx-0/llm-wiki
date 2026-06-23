// Atlas view — a hierarchical-graphical map of the knowledge base, inspired by
// understand-anything's layered knowledge graph. Three levels radiating out:
// vault → knowledge types → entries. Pan/zoom, glowing additive nodes coloured by
// type, animated radial entrance, hover-to-highlight + tooltip, click → Obsidian.
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
  x: number; y: number; r: number; color: [number, number, number];
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

const ENTRIES_PER_TYPE = 14; // cap per layer (graph stays legible)
const X_ROOT = -440, X_TYPE = 0, X_ENTRY = 300; // layered columns (left → right)
const EGAP = 15; // entry vertical gap

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

  const root: GNode = { id: 'root', kind: 'root', label: vaultName || 'vault', type: 'root', x: X_ROOT, y: 0, r: 24, color: NODE };
  nodes = [root];
  edges.length = 0;

  // allocate vertical space per type proportional to its (capped) entry count
  const blockH = (count: number) => Math.max(110, Math.min(count, ENTRIES_PER_TYPE) * EGAP + 50);
  let total = 0;
  for (const [, list] of types) total += blockH(list.length) + 36;
  let cursor = -total / 2;

  types.forEach(([type, list]) => {
    const h = blockH(list.length);
    const cy = cursor + h / 2;
    cursor += h + 36;
    const tn: GNode = {
      id: `t:${type}`, kind: 'type', label: `${type} · ${list.length}`, type,
      x: X_TYPE, y: cy, r: 8 + Math.min(14, Math.sqrt(list.length) * 1.5), color: colorOf(type), parent: root,
    };
    nodes.push(tn);
    edges.push([root, tn]);

    const shown = list.slice(0, ENTRIES_PER_TYPE);
    shown.forEach((e, ei) => {
      const en: GNode = {
        id: `e:${e.file}`, kind: 'entry', label: e.title, type: e.type, file: e.file,
        x: X_ENTRY, y: cy + (ei - (shown.length - 1) / 2) * EGAP, r: 3.5, color: colorOf(e.type), parent: tn,
      };
      nodes.push(en);
      edges.push([tn, en]);
    });
  });

  // fit the camera to the layered height
  zoom = Math.max(0.3, Math.min(0.85, (H - 150) / Math.max(total, 1)));
  panX = -((X_ROOT + X_ENTRY) / 2) * zoom;
  panY = 0;
}

// camera
let zoom = 0.62, panX = 0, panY = 0;
let reveal = 0; // entrance animation 0..1
let hover: GNode | null = null;
const toScreen = (x: number, y: number, rv: number) => ({ x: W / 2 + (x * rv) * zoom + panX, y: H / 2 + (y * rv) * zoom + panY });

function draw(now: number): void {
  reveal += (1 - reveal) * 0.04;
  const rv = reveal < 0.999 ? 1 - Math.pow(1 - reveal, 3) : 1; // ease-out expand from center
  const t = now / 1000;
  ctx.clearRect(0, 0, W, H);
  ctx.globalCompositeOperation = 'lighter';

  // edges
  for (const [a, b] of edges) {
    const pa = toScreen(a.x, a.y, rv), pb = toScreen(b.x, b.y, rv);
    const hot = hover && (a === hover || b === hover || a === hover?.parent || b === hover?.parent);
    ctx.strokeStyle = rgba(b.color, hot ? 0.6 : b.kind === 'entry' ? 0.12 : 0.26);
    ctx.lineWidth = hot ? 1.5 : b.kind === 'entry' ? 0.7 : 1.1;
    const mx = (pa.x + pb.x) / 2;
    ctx.beginPath();
    ctx.moveTo(pa.x, pa.y);
    ctx.bezierCurveTo(mx, pa.y, mx, pb.y, pb.x, pb.y); // horizontal-flow bezier (React-Flow style)
    ctx.stroke();
  }

  // nodes
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  for (const n of nodes) {
    const p = toScreen(n.x, n.y, rv);
    const isHover = n === hover;
    const pulse = n.kind === 'root' ? 1 + Math.sin(t * 1.5) * 0.06 : 1;
    const r = n.r * (isHover ? 1.4 : 1) * pulse * (0.5 + zoom * 0.6);
    ctx.beginPath();
    ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
    ctx.fillStyle = rgba(n.color, n.kind === 'entry' ? 0.85 : 1);
    ctx.shadowColor = rgba(n.color, 0.9);
    ctx.shadowBlur = (n.kind === 'entry' ? 6 : 16) * (isHover ? 1.6 : 1);
    ctx.fill();
  }
  ctx.shadowBlur = 0;

  ctx.globalCompositeOperation = 'source-over';

  // labels: root + type labels to the left of their node; entry labels to the right
  for (const n of nodes) {
    if (n.kind === 'entry' && zoom < 0.85 && n !== hover) continue;
    const p = toScreen(n.x, n.y, rv);
    const rr = n.r * (0.5 + zoom * 0.6);
    const label = n.label.length > 30 ? n.label.slice(0, 29) + '…' : n.label;
    if (n.kind === 'entry') {
      ctx.textAlign = 'left';
      ctx.font = `500 10.5px -apple-system, BlinkMacSystemFont, sans-serif`;
      ctx.fillStyle = n === hover ? '#fff' : 'rgba(226,232,240,0.72)';
      ctx.fillText(label, p.x + rr + 7, p.y);
    } else {
      ctx.textAlign = 'right';
      ctx.font = `600 13px -apple-system, BlinkMacSystemFont, sans-serif`;
      ctx.fillStyle = '#e2e8f0';
      ctx.fillText(label, p.x - rr - 8, p.y);
    }
  }
  ctx.textAlign = 'start';

  requestAnimationFrame(draw);
}

// ── interaction ──
function nodeAt(px: number, py: number): GNode | null {
  const rv = 1;
  let best: GNode | null = null, bd = 16 * 16;
  for (const n of nodes) {
    const p = toScreen(n.x, n.y, rv);
    const rr = Math.max(8, n.r * (0.5 + zoom * 0.6));
    const dx = p.x - px, dy = p.y - py, d = dx * dx + dy * dy;
    if (d < Math.max(bd, rr * rr) && d < rr * rr + 60) {
      if (d < bd) {
        bd = d;
        best = n;
      }
    }
  }
  return best;
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
      // focus the cluster: center it
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
  const f = Math.exp(-e.deltaY * 0.0012);
  const nz = Math.max(0.25, Math.min(3, zoom * f));
  // zoom around cursor
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
