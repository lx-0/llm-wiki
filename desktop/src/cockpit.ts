// Cockpit view — a full-window "neural net" sphere (rotating icosphere of glowing
// nodes + connections + orbiting particles + synapse pulses) with a glass HUD over
// it (vault stat, health, recent, ask). Inspired by lx-0/agent-kiosk's sphere theme;
// the icosphere construction is standard math, re-implemented + brand-coloured.
import './index.css';
import { marked } from 'marked';

// ─────────────────────────── icosphere (nodes + edges) ───────────────────────
function makeIcosphere(subdiv: number): { vertices: number[][]; edges: [number, number][] } {
  const phi = (1 + Math.sqrt(5)) / 2;
  const verts: number[][] = [
    [-1, phi, 0], [1, phi, 0], [-1, -phi, 0], [1, -phi, 0],
    [0, -1, phi], [0, 1, phi], [0, -1, -phi], [0, 1, -phi],
    [phi, 0, -1], [phi, 0, 1], [-phi, 0, -1], [-phi, 0, 1],
  ].map((v) => {
    const l = Math.hypot(v[0], v[1], v[2]);
    return [v[0] / l, v[1] / l, v[2] / l];
  });
  let faces: number[][] = [
    [0, 11, 5], [0, 5, 1], [0, 1, 7], [0, 7, 10], [0, 10, 11], [1, 5, 9], [5, 11, 4],
    [11, 10, 2], [10, 7, 6], [7, 1, 8], [3, 9, 4], [3, 4, 2], [3, 2, 6], [3, 6, 8],
    [3, 8, 9], [4, 9, 5], [2, 4, 11], [6, 2, 10], [8, 6, 7], [9, 8, 1],
  ];
  const mid: Record<string, number> = {};
  const midpoint = (a: number, b: number): number => {
    const key = a < b ? `${a}-${b}` : `${b}-${a}`;
    if (mid[key] !== undefined) return mid[key];
    const m = [(verts[a][0] + verts[b][0]) / 2, (verts[a][1] + verts[b][1]) / 2, (verts[a][2] + verts[b][2]) / 2];
    const l = Math.hypot(m[0], m[1], m[2]);
    verts.push([m[0] / l, m[1] / l, m[2] / l]);
    return (mid[key] = verts.length - 1);
  };
  for (let s = 0; s < subdiv; s++) {
    const nf: number[][] = [];
    for (const [a, b, c] of faces) {
      const ab = midpoint(a, b), bc = midpoint(b, c), ca = midpoint(c, a);
      nf.push([a, ab, ca], [ab, b, bc], [ca, bc, c], [ab, bc, ca]);
    }
    faces = nf;
  }
  const seen = new Set<string>();
  const edges: [number, number][] = [];
  for (const [a, b, c] of faces) {
    for (const [x, y] of [[a, b], [b, c], [c, a]] as [number, number][]) {
      const key = x < y ? `${x}-${y}` : `${y}-${x}`;
      if (!seen.has(key)) {
        seen.add(key);
        edges.push([x, y]);
      }
    }
  }
  return { vertices: verts, edges };
}

// ─────────────────────────── canvas + projection ─────────────────────────────
const canvas = document.getElementById('cockpit-canvas') as HTMLCanvasElement;
const ctx = canvas.getContext('2d')!;
let W = 0, H = 0, cx = 0, cy = 0, radius = 0;

function resize(): void {
  const dpr = window.devicePixelRatio || 1;
  W = canvas.clientWidth || window.innerWidth;
  H = canvas.clientHeight || window.innerHeight;
  canvas.width = Math.round(W * dpr);
  canvas.height = Math.round(H * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  cx = W / 2;
  cy = H * 0.46;
  radius = Math.min(W, H) * 0.26;
}
window.addEventListener('resize', resize);

const sphere = makeIcosphere(2);
const NODE: [number, number, number] = [125, 211, 252]; // sky #7dd3fc
const EDGE: [number, number, number] = [167, 139, 250]; // violet #a78bfa
const rgba = (c: [number, number, number], a: number) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;

type P = { x: number; y: number; z: number };
function project(v: number[], rotX: number, rotY: number): P {
  const x0 = v[0] * Math.cos(rotY) - v[2] * Math.sin(rotY);
  const z0 = v[0] * Math.sin(rotY) + v[2] * Math.cos(rotY);
  const y1 = v[1] * Math.cos(rotX) - z0 * Math.sin(rotX);
  const z1 = v[1] * Math.sin(rotX) + z0 * Math.cos(rotX);
  const s = 340 / (340 + z1 * radius * 0.55);
  return { x: cx + x0 * radius * s, y: cy + y1 * radius * s, z: z1 };
}

// orbiting particles
const orbits = [
  { speed: 0.22, rx: 1.35, ry: 0.34, phase: 0 },
  { speed: -0.16, rx: 1.2, ry: 0.26, phase: 1.7 },
  { speed: 0.12, rx: 1.5, ry: 0.2, phase: 3.1 },
];
const particles = Array.from({ length: 16 }, (_, i) => ({
  angle: (Math.PI * 2 / 16) * i,
  orbit: i % orbits.length,
  size: 1.4 + (i % 5) * 0.5,
}));

// synapse pulses travelling along edges
const pulses: { edge: number; t: number; speed: number }[] = [];
let pulseAccum = 0;

let last = 0;
function draw(now: number): void {
  const dt = last ? (now - last) / 1000 : 0;
  last = now;
  const t = now / 1000;
  ctx.clearRect(0, 0, W, H);

  // ambient core glow
  const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius * 2.4);
  g.addColorStop(0, rgba(EDGE, 0.16));
  g.addColorStop(0.5, rgba(EDGE, 0.05));
  g.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, W, H);

  const rotY = t * 0.18;
  const rotX = Math.sin(t * 0.12) * 0.28;
  const proj = sphere.vertices.map((v) => project(v, rotX, rotY));
  const depth = (z: number) => Math.max(0, Math.min(1, (z + 1.1) / 2.2));

  // edges (connections)
  ctx.lineWidth = 1;
  for (const [a, b] of sphere.edges) {
    const d = (depth(proj[a].z) + depth(proj[b].z)) / 2;
    ctx.strokeStyle = rgba(EDGE, 0.06 + d * 0.22);
    ctx.beginPath();
    ctx.moveTo(proj[a].x, proj[a].y);
    ctx.lineTo(proj[b].x, proj[b].y);
    ctx.stroke();
  }

  // nodes (glowing dots, depth-shaded)
  for (let i = 0; i < proj.length; i++) {
    const d = depth(proj[i].z);
    const r = 1.3 + d * 2.6;
    ctx.beginPath();
    ctx.arc(proj[i].x, proj[i].y, r, 0, Math.PI * 2);
    ctx.fillStyle = rgba(NODE, 0.3 + d * 0.6);
    ctx.shadowColor = rgba(NODE, 0.9);
    ctx.shadowBlur = 6 + d * 10;
    ctx.fill();
  }
  ctx.shadowBlur = 0;

  // synapse pulses
  pulseAccum += dt;
  if (pulseAccum > 0.18) {
    pulseAccum = 0;
    if (pulses.length < 24) pulses.push({ edge: Math.floor(Math.random() * sphere.edges.length), t: 0, speed: 0.8 + Math.random() * 0.9 });
  }
  for (let i = pulses.length - 1; i >= 0; i--) {
    const p = pulses[i];
    p.t += dt * p.speed;
    if (p.t >= 1) {
      pulses.splice(i, 1);
      continue;
    }
    const [a, b] = sphere.edges[p.edge];
    const x = proj[a].x + (proj[b].x - proj[a].x) * p.t;
    const y = proj[a].y + (proj[b].y - proj[a].y) * p.t;
    ctx.beginPath();
    ctx.arc(x, y, 2.4, 0, Math.PI * 2);
    ctx.fillStyle = rgba(NODE, 0.95 * (1 - p.t * 0.4));
    ctx.shadowColor = rgba(NODE, 1);
    ctx.shadowBlur = 12;
    ctx.fill();
  }
  ctx.shadowBlur = 0;

  // orbit particles
  for (const pt of particles) {
    const o = orbits[pt.orbit];
    pt.angle += dt * o.speed;
    const ox = cx + Math.cos(pt.angle + o.phase) * radius * o.rx;
    const oy = cy + Math.sin(pt.angle + o.phase) * radius * o.ry;
    ctx.beginPath();
    ctx.arc(ox, oy, pt.size, 0, Math.PI * 2);
    ctx.fillStyle = rgba(NODE, 0.55);
    ctx.shadowColor = rgba(NODE, 0.8);
    ctx.shadowBlur = 8;
    ctx.fill();
  }
  ctx.shadowBlur = 0;

  requestAnimationFrame(draw);
}

// ─────────────────────────── HUD data ────────────────────────────────────────
const FOLDER_CLS = (type: string) => type.replace(/[^a-zA-Z0-9]/g, '').toLowerCase() || 'note';
function esc(s: string): string {
  return s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c] as string);
}

async function loadHud(): Promise<void> {
  const v = await window.vault.status();
  const vaultEl = document.getElementById('ck-vault');
  const statEl = document.getElementById('ck-stat');
  const healthEl = document.getElementById('ck-health');
  const recentEl = document.getElementById('ck-recent-list');
  if (!v) {
    if (statEl) statEl.textContent = 'No vault found';
    return;
  }
  if (vaultEl) vaultEl.textContent = v.name;
  if (statEl) statEl.innerHTML = `<span class="ck-big">${v.articleCount.toLocaleString()}</span> notes`;
  if (recentEl) {
    recentEl.innerHTML = '';
    for (const r of v.recent ?? []) {
      const row = document.createElement('button');
      row.className = 'ck-recent-row';
      row.innerHTML = `<span class="type-badge t-${FOLDER_CLS(r.type)}">${esc(r.type)}</span><span class="ck-recent-title">${esc(r.title)}</span>`;
      row.addEventListener('click', () => window.vault.openFile(r.file));
      recentEl.appendChild(row);
    }
  }
  const d = await window.vault.doctor();
  if (healthEl && d) {
    healthEl.innerHTML =
      d.issues === 0
        ? `<span class="ok">● all systems healthy</span>`
        : `<span class="warn">⚠ ${d.issues} ${d.issues === 1 ? 'issue' : 'issues'}</span>`;
  }
}

// ask
let asking = false;
async function ask(): Promise<void> {
  const input = document.getElementById('ck-input') as HTMLInputElement | null;
  const answer = document.getElementById('ck-answer');
  const btn = document.getElementById('ck-ask-btn') as HTMLButtonElement | null;
  if (!input || !answer || asking) return;
  const q = input.value.trim();
  if (!q) return;
  asking = true;
  if (btn) btn.disabled = true;
  answer.hidden = false;
  answer.className = 'ck-answer thinking';
  answer.textContent = 'Thinking…';
  try {
    const res = await window.vault.query(q);
    answer.className = 'ck-answer' + (res.ok ? '' : ' err');
    answer.innerHTML = res.ok
      ? marked.parse(res.answer.replace(/\[\[([^\]]+)\]\]/g, (_m, p: string) => esc((p.split('|')[0].split('#')[0].split('/').pop() || p).trim())), { breaks: true, async: false }) as string
      : esc(res.answer || 'No answer.');
  } catch {
    answer.className = 'ck-answer err';
    answer.textContent = 'Something went wrong.';
  } finally {
    asking = false;
    if (btn) btn.disabled = false;
  }
}

// ─────────────────────────── wire up ─────────────────────────────────────────
resize();
requestAnimationFrame(draw);
void loadHud();
document.getElementById('ck-ask-btn')?.addEventListener('click', () => void ask());
document.getElementById('ck-input')?.addEventListener('keydown', (e) => {
  if ((e as KeyboardEvent).key === 'Enter') void ask();
});
document.getElementById('ck-compact')?.addEventListener('click', () => window.app.closeCockpit());
document.getElementById('ck-input')?.focus();
