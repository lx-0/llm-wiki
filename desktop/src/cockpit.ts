// Cockpit view — a full-window "neural net" sphere with a glass HUD. Adapted from
// lx-0/agent-kiosk's sophia sphere theme (icosphere math + the layered look:
// massive glow halo, breathing hot core, inner filled crystal, cubic depth-falloff
// wireframe, blob deformation, scanlines, synapse pulses), re-implemented and
// brand-coloured (violet glow + cyan wireframe). Reactive to engine activity.
import './index.css';
import { marked } from 'marked';

// ─────────────────────────── icosphere (nodes + edges + faces) ───────────────
function makeIcosphere(subdiv: number): { vertices: number[][]; edges: [number, number][]; faces: number[][] } {
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
  return { vertices: verts, edges, faces };
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
  radius = Math.min(W * 0.62, H) * 0.32;
}
window.addEventListener('resize', resize);

const outer = makeIcosphere(2);
const inner = makeIcosphere(1);
const GLOW: [number, number, number] = [167, 139, 250]; // violet #a78bfa
const NODE: [number, number, number] = [125, 211, 252]; // cyan/sky #7dd3fc
const WARM: [number, number, number] = [255, 159, 64]; // amber bleed when issues
const rgba = (c: [number, number, number], a: number) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;

function noise3D(x: number, y: number, z: number): number {
  return Math.sin(x * 2.1 + y * 1.3) * Math.cos(y * 1.7 + z * 2.3) * Math.sin(z * 1.9 + x * 1.1);
}

type P = { x: number; y: number; z: number };
function project(v: number[], rotX: number, rotY: number, deform: number, t: number): P {
  const n = noise3D(v[0] * 2 + t * 0.5, v[1] * 2 + t * 0.3, v[2] * 2 + t * 0.4) * deform;
  const sc = 1 + n;
  const vx = v[0] * sc, vy = v[1] * sc, vz = v[2] * sc;
  const x0 = vx * Math.cos(rotY) - vz * Math.sin(rotY);
  const z0 = vx * Math.sin(rotY) + vz * Math.cos(rotY);
  const y1 = vy * Math.cos(rotX) - z0 * Math.sin(rotX);
  const z1 = vy * Math.sin(rotX) + z0 * Math.cos(rotX);
  const s = 340 / (340 + z1 * radius * 0.55);
  return { x: cx + x0 * radius * s, y: cy + y1 * radius * s, z: z1 };
}

// orbiting particles
const orbits = [
  { speed: 0.22, rx: 1.4, ry: 0.36, phase: 0 },
  { speed: -0.16, rx: 1.22, ry: 0.26, phase: 1.7 },
  { speed: 0.12, rx: 1.55, ry: 0.2, phase: 3.1 },
];
const particles = Array.from({ length: 16 }, (_, i) => ({ angle: (Math.PI * 2 / 16) * i, orbit: i % 3, size: 1.4 + (i % 5) * 0.5 }));

// synapse pulses travelling along edges
const pulses: { edge: number; t: number; speed: number }[] = [];
let pulseAccum = 0;

// reactive state
let energy = 0.35; // 0..1, ramps when an engine job runs
let targetEnergy = 0.35;
let hasIssues = false;
let thinking = false; // a question is being answered

// "question threads into the net": glowing particles fly from the Ask card into
// random sphere nodes when you submit a question.
type Feed = { sx: number; sy: number; node: number; t: number; speed: number };
const feeds: Feed[] = [];
function igniteFromAsk(): void {
  const rect = document.getElementById('ck-input')?.getBoundingClientRect();
  const sx = rect ? rect.left + rect.width / 2 : cx;
  const sy = rect ? rect.top : cy + radius;
  for (let i = 0; i < 20; i++) {
    feeds.push({
      sx: sx + (Math.random() - 0.5) * (rect?.width ?? 200) * 0.7,
      sy: sy + (Math.random() - 0.5) * 8,
      node: Math.floor(Math.random() * outer.vertices.length),
      t: -i * 0.025, // staggered launch
      speed: 0.9 + Math.random() * 0.7,
    });
  }
  thinking = true;
  targetEnergy = 1;
}
// mouse parallax
let mx = 0, my = 0, pRotX = 0, pRotY = 0;
window.addEventListener('mousemove', (e) => {
  mx = (e.clientX / W - 0.5) * 2;
  my = (e.clientY / H - 0.5) * 2;
});

let last = 0;
function draw(now: number): void {
  const dt = last ? Math.min(0.05, (now - last) / 1000) : 0;
  last = now;
  const t = now / 1000;
  energy += (targetEnergy - energy) * Math.min(1, dt * 2.5);
  pRotX += (my * 0.22 - pRotX) * Math.min(1, dt * 3);
  pRotY += (mx * 0.3 - pRotY) * Math.min(1, dt * 3);
  ctx.clearRect(0, 0, W, H);

  const rotY = t * (0.12 + energy * 0.18) + pRotY;
  const rotX = Math.sin(t * 0.12) * 0.26 + pRotX;
  const deform = 0.05 + energy * 0.05 + Math.sin(t * 0.7) * 0.02;
  const glowC = hasIssues ? WARM : GLOW;

  // ─── massive glow halo (layered) ───
  for (let i = 0; i < 3; i++) {
    const r = radius * (2.5 - i * 0.5);
    const a = (0.16 + energy * 0.1) - i * 0.04;
    const g = ctx.createRadialGradient(cx + Math.sin(t * 0.7) * 8, cy + Math.cos(t * 0.5) * 6, 0, cx, cy, r);
    g.addColorStop(0, rgba(glowC, a));
    g.addColorStop(0.3, rgba(glowC, a * 0.55));
    g.addColorStop(0.6, rgba(glowC, a * 0.2));
    g.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H);
  }

  // ─── breathing hot core ───
  const blobR = radius * (0.5 + Math.sin(t * 1.1) * 0.07);
  const gb = ctx.createRadialGradient(cx + Math.sin(t * 0.6) * 14, cy + Math.cos(t * 0.8) * 11, 0, cx, cy, blobR);
  gb.addColorStop(0, rgba(glowC, 0.32 + Math.sin(t * 1.5) * 0.06 + energy * 0.1));
  gb.addColorStop(0.45, rgba(glowC, 0.18));
  gb.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = gb;
  ctx.fillRect(0, 0, W, H);

  const rotXn = rotX, rotYn = rotY;
  const projOuter = outer.vertices.map((v) => project(v, rotXn, rotYn, deform, t));
  const projInner = inner.vertices.map((v) => project([v[0] * 0.62, v[1] * 0.62, v[2] * 0.62], rotXn, rotYn, deform * 1.7, t * 1.3));

  // ─── inner crystal: filled semi-transparent faces (painter's algorithm) ───
  inner.faces
    .map((f) => {
      const pts = f.map((i) => projInner[i]);
      return { pts, z: (pts[0].z + pts[1].z + pts[2].z) / 3 };
    })
    .sort((a, b) => a.z - b.z)
    .forEach(({ pts, z }) => {
      if (z < -0.4) return;
      const front = Math.max(0, (z + 0.4) / 1.4);
      ctx.beginPath();
      ctx.moveTo(pts[0].x, pts[0].y);
      ctx.lineTo(pts[1].x, pts[1].y);
      ctx.lineTo(pts[2].x, pts[2].y);
      ctx.closePath();
      ctx.fillStyle = rgba(glowC, 0.04 + front * 0.16);
      ctx.fill();
      ctx.strokeStyle = rgba(glowC, 0.08 + front * 0.22);
      ctx.lineWidth = 0.6;
      ctx.stroke();
    });

  // ─── outer wireframe (aggressive cubic depth falloff) ───
  for (const [a, b] of outer.edges) {
    const z = (projOuter[a].z + projOuter[b].z) / 2;
    const d01 = (z + 1) / 2;
    const br = Math.pow(d01, 2.6) * 0.7;
    if (br < 0.015) continue;
    ctx.beginPath();
    ctx.moveTo(projOuter[a].x, projOuter[a].y);
    ctx.lineTo(projOuter[b].x, projOuter[b].y);
    ctx.strokeStyle = rgba(NODE, br);
    ctx.lineWidth = 0.4 + d01 * 0.7;
    ctx.stroke();
  }

  // ─── outer nodes (depth-shaded glowing dots) ───
  for (const p of projOuter) {
    const d01 = (p.z + 1) / 2;
    if (d01 < 0.18) continue;
    const a = Math.pow(d01, 1.5) * 0.95;
    const r = 0.8 + d01 * 2.4;
    ctx.beginPath();
    ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
    ctx.fillStyle = rgba(NODE, a);
    if (d01 > 0.45) {
      ctx.shadowColor = rgba(NODE, 0.9);
      ctx.shadowBlur = 5 + d01 * 9;
    }
    ctx.fill();
    ctx.shadowBlur = 0;
  }

  // ─── synapse pulses (rate scales with energy) ───
  pulseAccum += dt;
  if (pulseAccum > 0.16 - energy * 0.11) {
    pulseAccum = 0;
    if (pulses.length < 40) pulses.push({ edge: Math.floor(Math.random() * outer.edges.length), t: 0, speed: 0.8 + Math.random() * 1.0 });
  }
  for (let i = pulses.length - 1; i >= 0; i--) {
    const p = pulses[i];
    p.t += dt * p.speed;
    if (p.t >= 1) {
      pulses.splice(i, 1);
      continue;
    }
    const [a, b] = outer.edges[p.edge];
    if ((projOuter[a].z + projOuter[b].z) / 2 < -0.5) continue;
    const x = projOuter[a].x + (projOuter[b].x - projOuter[a].x) * p.t;
    const y = projOuter[a].y + (projOuter[b].y - projOuter[a].y) * p.t;
    ctx.beginPath();
    ctx.arc(x, y, 2.3, 0, Math.PI * 2);
    ctx.fillStyle = rgba(NODE, 0.95 * (1 - p.t * 0.3));
    ctx.shadowColor = rgba(NODE, 1);
    ctx.shadowBlur = 13;
    ctx.fill();
    ctx.shadowBlur = 0;
  }

  // ─── scanlines (faint hologram texture across the orb) ───
  for (let y = cy - radius; y < cy + radius; y += 6) {
    const dy = (y - cy) / radius;
    const hw = Math.sqrt(Math.max(0, 1 - dy * dy)) * radius;
    ctx.beginPath();
    ctx.moveTo(cx - hw, y);
    ctx.lineTo(cx + hw, y);
    ctx.strokeStyle = rgba(NODE, 0.03 + Math.sin(y * 0.5 + t * 3) * 0.015);
    ctx.lineWidth = 0.5;
    ctx.stroke();
  }

  // ─── orbit particles ───
  for (const pt of particles) {
    const o = orbits[pt.orbit];
    pt.angle += dt * o.speed;
    const ox = cx + Math.cos(pt.angle + o.phase) * radius * o.rx;
    const oy = cy + Math.sin(pt.angle + o.phase) * radius * o.ry;
    ctx.beginPath();
    ctx.arc(ox, oy, pt.size, 0, Math.PI * 2);
    ctx.fillStyle = rgba(NODE, 0.5);
    ctx.shadowColor = rgba(NODE, 0.8);
    ctx.shadowBlur = 8;
    ctx.fill();
    ctx.shadowBlur = 0;
  }

  // ─── question feed: particles threading from the Ask card into the net ───
  for (let i = feeds.length - 1; i >= 0; i--) {
    const f = feeds[i];
    f.t += dt * f.speed;
    if (f.t < 0) continue;
    if (f.t >= 1) {
      pulses.push({ edge: Math.floor(Math.random() * outer.edges.length), t: 0, speed: 1.3 }); // arrival fires the net
      feeds.splice(i, 1);
      continue;
    }
    const tgt = projOuter[f.node];
    const e = f.t < 0.5 ? 2 * f.t * f.t : 1 - Math.pow(-2 * f.t + 2, 2) / 2; // easeInOut
    const x = f.sx + (tgt.x - f.sx) * e;
    const y = f.sy + (tgt.y - f.sy) * e;
    const ep = Math.max(0, e - 0.06);
    ctx.beginPath();
    ctx.moveTo(f.sx + (tgt.x - f.sx) * ep, f.sy + (tgt.y - f.sy) * ep);
    ctx.lineTo(x, y);
    ctx.strokeStyle = rgba(NODE, 0.45 * (1 - f.t * 0.3));
    ctx.lineWidth = 1.4;
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(x, y, 2.2, 0, Math.PI * 2);
    ctx.fillStyle = rgba(NODE, 0.95);
    ctx.shadowColor = rgba(NODE, 1);
    ctx.shadowBlur = 12;
    ctx.fill();
    ctx.shadowBlur = 0;
  }

  requestAnimationFrame(draw);
}

// ─────────────────────────── HUD ─────────────────────────────────────────────
const clsOf = (type: string) => type.replace(/[^a-zA-Z0-9]/g, '').toLowerCase() || 'note';
function esc(s: string): string {
  return s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c] as string);
}

let countRaf = 0;
function countUp(el: HTMLElement, to: number): void {
  const start = performance.now();
  cancelAnimationFrame(countRaf);
  const step = (n: number): void => {
    const k = Math.min(1, (n - start) / 800);
    const val = Math.round(to * (1 - Math.pow(1 - k, 3)));
    el.innerHTML = `<span class="ck-big">${val.toLocaleString()}</span> notes`;
    if (k < 1) countRaf = requestAnimationFrame(step);
  };
  countRaf = requestAnimationFrame(step);
}

async function loadHud(): Promise<void> {
  const v = await window.vault.status();
  const vaultEl = document.getElementById('ck-vault');
  const statEl = document.getElementById('ck-stat');
  const recentEl = document.getElementById('ck-recent-list');
  if (!v) {
    if (statEl) statEl.textContent = 'No vault found';
    return;
  }
  if (vaultEl) vaultEl.textContent = v.name;
  if (statEl) countUp(statEl, v.articleCount);
  if (recentEl) {
    recentEl.innerHTML = '';
    for (const r of v.recent ?? []) {
      const row = document.createElement('button');
      row.className = 'ck-recent-row';
      row.innerHTML = `<span class="type-badge t-${clsOf(r.type)}">${esc(r.type)}</span><span class="ck-recent-title">${esc(r.title)}</span>`;
      row.addEventListener('click', () => window.vault.openFile(r.file));
      recentEl.appendChild(row);
    }
  }
  void loadTypes();
  void loadDoctor();
  void loadPending();
}

async function loadTypes(): Promise<void> {
  const el = document.getElementById('ck-types');
  if (!el) return;
  const entries = await window.vault.list();
  const counts: Record<string, number> = {};
  for (const e of entries) counts[e.type] = (counts[e.type] || 0) + 1;
  const top = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 5);
  el.innerHTML = top
    .map(([type, n]) => `<span class="ck-type-chip"><span class="type-badge t-${clsOf(type)}">${esc(type)}</span>${n}</span>`)
    .join('');
}

async function loadDoctor(): Promise<void> {
  const el = document.getElementById('ck-health');
  const d = await window.vault.doctor();
  hasIssues = !!d && d.issues > 0;
  if (el && d) {
    el.innerHTML =
      d.issues === 0
        ? `<span class="ok">● all systems healthy</span>`
        : `<span class="warn">⚠ ${d.issues} ${d.issues === 1 ? 'issue' : 'issues'}</span>`;
  }
}

// ── actions (Update + pending suggestions) — reactive sphere on run ──
let busy = false;
function setBusy(b: boolean): void {
  busy = b;
  targetEnergy = b ? 1 : 0.35;
  const u = document.getElementById('ck-update') as HTMLButtonElement | null;
  if (u) {
    u.disabled = b;
    u.textContent = b ? 'Working…' : 'Update knowledge';
  }
}

async function loadPending(): Promise<void> {
  const el = document.getElementById('ck-pending-list');
  if (!el) return;
  const m = await window.vault.menu();
  const items = (m?.suggestions ?? []).slice(0, 5);
  el.innerHTML = '';
  if (items.length === 0) {
    el.innerHTML = `<div class="ck-empty">Nothing pending 🎉</div>`;
    return;
  }
  for (const s of items) {
    const row = document.createElement('div');
    row.className = 'ck-pending-row';
    row.innerHTML = `<span class="ck-pending-label">${esc(s.label)}</span>`;
    const b = document.createElement('button');
    b.className = 'ck-run';
    b.textContent = 'Run';
    b.disabled = busy;
    b.addEventListener('click', () => {
      if (busy) return;
      setBusy(true);
      void window.vault.runArgs(s.cmd.split(/\s+/));
    });
    row.appendChild(b);
    el.appendChild(row);
  }
}

document.getElementById('ck-update')?.addEventListener('click', () => {
  if (busy) return;
  setBusy(true);
  void window.vault.compile();
});
window.vault.onCompileDone(() => {
  setBusy(false);
  void loadHud();
});
window.vault.onRunDone(() => {
  setBusy(false);
  void loadHud();
});

// poll engine busy-state so the sphere reacts even to jobs started elsewhere
setInterval(() => {
  void window.vault.runStatus().then((s) => {
    if (!busy && !thinking) targetEnergy = s.running ? 1 : 0.35;
  });
}, 1500);

// ── ask ──
let asking = false;
async function ask(): Promise<void> {
  const input = document.getElementById('ck-input') as HTMLInputElement | null;
  const answer = document.getElementById('ck-answer');
  const btn = document.getElementById('ck-ask-btn') as HTMLButtonElement | null;
  if (!input || !answer || asking) return;
  const q = input.value.trim();
  if (!q) return;
  asking = true;
  igniteFromAsk(); // question threads into the net + the sphere ramps up
  if (btn) btn.disabled = true;
  answer.hidden = false;
  answer.className = 'ck-answer thinking';
  answer.textContent = 'Thinking…';
  try {
    const res = await window.vault.query(q);
    answer.className = 'ck-answer' + (res.ok ? '' : ' err');
    answer.innerHTML = res.ok
      ? (marked.parse(
          res.answer.replace(/\[\[([^\]]+)\]\]/g, (_m, p: string) => esc((p.split('|')[0].split('#')[0].split('/').pop() || p).trim())),
          { breaks: true, async: false },
        ) as string)
      : esc(res.answer || 'No answer.');
  } catch {
    answer.className = 'ck-answer err';
    answer.textContent = 'Something went wrong.';
  } finally {
    asking = false;
    thinking = false;
    if (!busy) targetEnergy = 0.35;
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
