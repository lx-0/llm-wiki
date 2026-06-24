// Cockpit view — a living "neural net" of the actual knowledge base. The sphere's
// nodes ARE entries (type-coloured, clickable → Obsidian); additive bloom, a
// starfield, a breathing violet core, constellation labels of recent entries, and
// answer shockwaves. Asking sends the question's letters orbiting playfully around
// the net while the brain "thinks". Adapted from lx-0/agent-kiosk's sophia sphere,
// re-implemented + brand-coloured + data-driven.
import './index.css';
import { friendlyPending } from './lib/pending';
import { marked } from 'marked';

const ICO_COPY = `<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`;
const ICO_CHECK = `<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>`;
const ICO_X = `<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18M6 6l12 12"/></svg>`;

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

const outer = makeIcosphere(2);
const inner = makeIcosphere(1);
const GLOW: [number, number, number] = [167, 139, 250]; // violet
const NODE: [number, number, number] = [125, 211, 252]; // cyan
const WARM: [number, number, number] = [255, 159, 64];
const rgba = (c: [number, number, number], a: number) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;

// the sphere IS the knowledge graph — nodes mapped to real entries, coloured by type
const TYPE_COLOR: Record<string, [number, number, number]> = {
  person: [224, 82, 176], project: [26, 184, 200], concept: [148, 132, 240],
  fact: [224, 86, 79], area: [52, 200, 110], map: [230, 180, 30], link: [240, 150, 70],
};
type NodeEntry = { type: string; file: string; title: string } | null;
let nodeEntries: NodeEntry[] = [];
const nodeColor = (i: number): [number, number, number] => {
  const e = nodeEntries[i];
  return e ? TYPE_COLOR[e.type] ?? NODE : NODE;
};
type P = { x: number; y: number; z: number };
let lastProj: P[] = [];
const ripples: { t: number }[] = [];
let stars: { x: number; y: number; a: number; tw: number }[] = [];

function genStars(): void {
  stars = Array.from({ length: 90 }, () => ({ x: Math.random() * W, y: Math.random() * H, a: 0.05 + Math.random() * 0.22, tw: Math.random() * Math.PI * 2 }));
}
function resize(): void {
  // Cap the device-pixel-ratio: on a retina display rendering at 2× means 4× the
  // pixels for the (soft) glow fills. 1.5× is visually indistinguishable here but
  // ~44% less fill work.
  const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
  W = canvas.clientWidth || window.innerWidth;
  H = canvas.clientHeight || window.innerHeight;
  canvas.width = Math.round(W * dpr);
  canvas.height = Math.round(H * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  cx = W / 2;
  cy = H * 0.46;
  radius = Math.min(W * 0.62, H) * 0.32;
  genStars();
}
window.addEventListener('resize', resize);

function noise3D(x: number, y: number, z: number): number {
  return Math.sin(x * 2.1 + y * 1.3) * Math.cos(y * 1.7 + z * 2.3) * Math.sin(z * 1.9 + x * 1.1);
}
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

const orbits = [
  { speed: 0.22, rx: 1.42, ry: 0.36, phase: 0 },
  { speed: -0.16, rx: 1.24, ry: 0.26, phase: 1.7 },
  { speed: 0.12, rx: 1.58, ry: 0.2, phase: 3.1 },
];
const particles = Array.from({ length: 16 }, (_, i) => ({ angle: (Math.PI * 2 / 16) * i, orbit: i % 3, size: 1.4 + (i % 5) * 0.5 }));
const pulses: { edge: number; t: number; speed: number }[] = [];
let pulseAccum = 0;

// reactive + interaction state
let energy = 0.35, targetEnergy = 0.35, hasIssues = false, thinking = false;
let mx = 0, my = 0, pRotX = 0, pRotY = 0;
window.addEventListener('mousemove', (e) => {
  mx = (e.clientX / W - 0.5) * 2;
  my = (e.clientY / H - 0.5) * 2;
});

// question letters orbiting the net
type Letter = { ch: string; a0: number; orbR: number; speed: number; tilt: number };
let letters: Letter[] = [];
let letterAlpha = 0;
function igniteFromAsk(q: string): void {
  const chars = q.replace(/\s+/g, ' ').trim().split('').slice(0, 48);
  letters = chars.map((ch, i) => ({
    ch,
    a0: (i / Math.max(1, chars.length)) * Math.PI * 2 + Math.random() * 0.25,
    orbR: 1.5 + Math.random() * 0.4,
    speed: 0.45 + Math.random() * 0.3,
    tilt: (Math.random() - 0.5) * 1.2,
  }));
  thinking = true;
  targetEnergy = 1;
}

// ── "enorm" extras ──
let hoverNode = -1;
const BLUE: [number, number, number] = [110, 165, 255];
const PINK: [number, number, number] = [224, 82, 176];
function auroraGlow(t: number): [number, number, number] {
  const k = (Math.sin(t * 0.13) + 1) / 2;
  return [GLOW[0] + (BLUE[0] - GLOW[0]) * k, GLOW[1] + (BLUE[1] - GLOW[1]) * k, GLOW[2] + (BLUE[2] - GLOW[2]) * k];
}
const arcs: { a: number; b: number; t: number; speed: number }[] = []; // thought-arcs between concepts
let arcAccum = 0;
const flares: { node: number; t: number }[] = []; // idle memories surfacing
let flareAccum = 0;
// drag-to-spin
let userRotY = 0, velY = 0, userRotX = 0, velX = 0;
let dragging = false, lastX = 0, lastY = 0, downX = 0, downY = 0;
// HUD panels tethered to the brain
const tetherEls = ['.ck-pending', '.ck-recent', '.ck-ask']
  .map((s) => document.querySelector(s))
  .filter(Boolean) as HTMLElement[];

let last = 0;
function draw(now: number): void {
  const dt = last ? Math.min(0.05, (now - last) / 1000) : 0;
  last = now;
  const t = now / 1000;
  energy += (targetEnergy - energy) * Math.min(1, dt * 2.5);
  pRotX += (my * 0.22 - pRotX) * Math.min(1, dt * 3);
  pRotY += (mx * 0.3 - pRotY) * Math.min(1, dt * 3);
  ctx.clearRect(0, 0, W, H);

  userRotY += velY;
  velY *= 0.94;
  userRotX = Math.max(-1.2, Math.min(1.2, userRotX + velX));
  velX *= 0.94;
  const rotY = t * (0.12 + energy * 0.18) + pRotY + userRotY;
  const rotX = Math.sin(t * 0.12) * 0.26 + pRotX + userRotX;
  const deform = 0.05 + energy * 0.05 + Math.sin(t * 0.7) * 0.02;
  const glowC = hasIssues ? WARM : auroraGlow(t);
  const projOuter = outer.vertices.map((v) => project(v, rotX, rotY, deform, t));
  const projInner = inner.vertices.map((v) => project([v[0] * 0.62, v[1] * 0.62, v[2] * 0.62], rotX, rotY, deform * 1.7, t * 1.3));
  lastProj = projOuter;

  ctx.globalCompositeOperation = 'lighter'; // additive bloom for everything luminous

  // starfield
  for (const s of stars) {
    const tw = 0.5 + 0.5 * Math.sin(t * 1.4 + s.tw);
    ctx.fillStyle = rgba([200, 220, 255], s.a * tw);
    ctx.fillRect(s.x, s.y, 1.3, 1.3);
  }

  // drifting nebula clouds — atmosphere + depth
  const nebs: { x: number; y: number; r: number; c: [number, number, number]; a: number }[] = [
    { x: cx - radius * 1.7, y: cy - radius * 0.9, r: radius * 2.3, c: GLOW, a: 0.05 },
    { x: cx + radius * 1.8, y: cy + radius * 1.1, r: radius * 2.6, c: BLUE, a: 0.045 },
    { x: cx + radius * 0.5, y: cy - radius * 1.7, r: radius * 1.9, c: PINK, a: 0.03 },
  ];
  for (const nb of nebs) {
    const dx = Math.sin(t * 0.08 + nb.r) * 32;
    const dy = Math.cos(t * 0.06 + nb.r) * 26;
    const g = ctx.createRadialGradient(nb.x + dx, nb.y + dy, 0, nb.x + dx, nb.y + dy, nb.r);
    g.addColorStop(0, rgba(nb.c, nb.a));
    g.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H);
  }

  // glow halo — one multi-stop radial (was 3 stacked full-screen fills)
  const HR = radius * 2.5;
  const ha = 0.17 + energy * 0.1;
  const g = ctx.createRadialGradient(cx + Math.sin(t * 0.7) * 8, cy + Math.cos(t * 0.5) * 6, 0, cx, cy, HR);
  g.addColorStop(0, rgba(glowC, ha));
  g.addColorStop(0.16, rgba(glowC, ha * 0.62));
  g.addColorStop(0.36, rgba(glowC, ha * 0.3));
  g.addColorStop(0.62, rgba(glowC, ha * 0.1));
  g.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, W, H);
  // breathing hot core — fill only its bounding box, not the whole screen
  const blobR = radius * (0.5 + Math.sin(t * 1.1) * 0.07);
  const gb = ctx.createRadialGradient(cx + Math.sin(t * 0.6) * 14, cy + Math.cos(t * 0.8) * 11, 0, cx, cy, blobR);
  gb.addColorStop(0, rgba(glowC, 0.26 + Math.sin(t * 1.5) * 0.05 + energy * 0.1));
  gb.addColorStop(0.45, rgba(glowC, 0.14));
  gb.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = gb;
  ctx.fillRect(cx - blobR - 24, cy - blobR - 24, blobR * 2 + 48, blobR * 2 + 48);

  // inner crystal (painter-sorted faces)
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
      ctx.fillStyle = rgba(glowC, 0.03 + front * 0.1);
      ctx.fill();
      ctx.strokeStyle = rgba(glowC, 0.05 + front * 0.16);
      ctx.lineWidth = 0.6;
      ctx.stroke();
    });

  // outer wireframe (cubic depth falloff)
  for (const [a, b] of outer.edges) {
    const z = (projOuter[a].z + projOuter[b].z) / 2;
    const d01 = (z + 1) / 2;
    const br = Math.pow(d01, 2.6) * 0.55;
    if (br < 0.015) continue;
    ctx.beginPath();
    ctx.moveTo(projOuter[a].x, projOuter[a].y);
    ctx.lineTo(projOuter[b].x, projOuter[b].y);
    ctx.strokeStyle = rgba(NODE, br);
    ctx.lineWidth = 0.4 + d01 * 0.7;
    ctx.stroke();
  }

  // outer nodes (type-coloured, depth-shaded)
  for (let i = 0; i < projOuter.length; i++) {
    const p = projOuter[i];
    const d01 = (p.z + 1) / 2;
    if (d01 < 0.16) continue;
    const c = nodeColor(i);
    const a = Math.pow(d01, 1.4) * 0.95;
    const r = 0.9 + d01 * 2.8;
    ctx.beginPath();
    ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
    ctx.fillStyle = rgba(c, a);
    ctx.shadowColor = rgba(c, 0.9);
    ctx.shadowBlur = 6 + d01 * 12;
    ctx.fill();
  }
  ctx.shadowBlur = 0;

  // scanlines
  for (let y = cy - radius; y < cy + radius; y += 6) {
    const dy = (y - cy) / radius;
    const hw = Math.sqrt(Math.max(0, 1 - dy * dy)) * radius;
    ctx.beginPath();
    ctx.moveTo(cx - hw, y);
    ctx.lineTo(cx + hw, y);
    ctx.strokeStyle = rgba(NODE, 0.025 + Math.sin(y * 0.5 + t * 3) * 0.012);
    ctx.lineWidth = 0.5;
    ctx.stroke();
  }

  // synapse pulses
  pulseAccum += dt;
  if (pulseAccum > 0.16 - energy * 0.11) {
    pulseAccum = 0;
    if (pulses.length < 24) pulses.push({ edge: Math.floor(Math.random() * outer.edges.length), t: 0, speed: 0.8 + Math.random() * 1.0 });
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
  }
  ctx.shadowBlur = 0;

  // thought-arcs: bright beams occasionally connecting two entry-nodes (ideas linking)
  arcAccum += dt;
  if (arcAccum > 1.4 - energy * 0.8 && arcs.length < 5) {
    arcAccum = 0;
    const ne: number[] = [];
    for (let i = 0; i < nodeEntries.length; i++) if (nodeEntries[i]) ne.push(i);
    if (ne.length > 2) {
      const a = ne[Math.floor(Math.random() * ne.length)];
      let b = ne[Math.floor(Math.random() * ne.length)];
      if (b === a) b = ne[(ne.indexOf(a) + 3) % ne.length];
      arcs.push({ a, b, t: 0, speed: 0.5 + Math.random() * 0.4 });
    }
  }
  for (let i = arcs.length - 1; i >= 0; i--) {
    const ar = arcs[i];
    ar.t += dt * ar.speed;
    if (ar.t >= 1) {
      arcs.splice(i, 1);
      continue;
    }
    const pa = projOuter[ar.a], pb = projOuter[ar.b];
    const ox = (pa.x + pb.x) / 2 + ((pa.x + pb.x) / 2 - cx) * 0.45;
    const oy = (pa.y + pb.y) / 2 + ((pa.y + pb.y) / 2 - cy) * 0.45;
    const fade = Math.sin(ar.t * Math.PI);
    ctx.beginPath();
    ctx.moveTo(pa.x, pa.y);
    ctx.quadraticCurveTo(ox, oy, pb.x, pb.y);
    ctx.strokeStyle = rgba(NODE, 0.28 * fade);
    ctx.lineWidth = 1.1;
    ctx.shadowColor = rgba(NODE, fade);
    ctx.shadowBlur = 6;
    ctx.stroke();
    ctx.shadowBlur = 0;
    const u = ar.t, iu = 1 - u;
    const qx = iu * iu * pa.x + 2 * iu * u * ox + u * u * pb.x;
    const qy = iu * iu * pa.y + 2 * iu * u * oy + u * u * pb.y;
    ctx.beginPath();
    ctx.arc(qx, qy, 2.6, 0, Math.PI * 2);
    ctx.fillStyle = rgba(NODE, 0.9 * fade);
    ctx.shadowColor = rgba(NODE, 1);
    ctx.shadowBlur = 12;
    ctx.fill();
    ctx.shadowBlur = 0;
  }

  // idle flares: a memory surfaces — a random front node pulses
  flareAccum += dt;
  if (flareAccum > 2.6 && flares.length < 2) {
    flareAccum = 0;
    const front: number[] = [];
    for (let i = 0; i < projOuter.length; i++) if (nodeEntries[i] && (projOuter[i].z + 1) / 2 > 0.6) front.push(i);
    if (front.length) flares.push({ node: front[Math.floor(Math.random() * front.length)], t: 0 });
  }
  for (let i = flares.length - 1; i >= 0; i--) {
    const fl = flares[i];
    fl.t += dt * 0.6;
    if (fl.t >= 1) {
      flares.splice(i, 1);
      continue;
    }
    const p = projOuter[fl.node];
    const fade = Math.sin(fl.t * Math.PI);
    const c = nodeColor(fl.node);
    ctx.beginPath();
    ctx.arc(p.x, p.y, 4 + fl.t * 24, 0, Math.PI * 2);
    ctx.strokeStyle = rgba(c, 0.55 * fade);
    ctx.lineWidth = 1.5 * fade + 0.3;
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(p.x, p.y, 3, 0, Math.PI * 2);
    ctx.fillStyle = rgba(c, fade);
    ctx.shadowColor = rgba(c, 1);
    ctx.shadowBlur = 14;
    ctx.fill();
    ctx.shadowBlur = 0;
  }

  // hovered node: flare it + light its connections
  if (hoverNode >= 0 && projOuter[hoverNode]) {
    const hp = projOuter[hoverNode];
    for (const [a, b] of outer.edges) {
      if (a !== hoverNode && b !== hoverNode) continue;
      ctx.beginPath();
      ctx.moveTo(projOuter[a].x, projOuter[a].y);
      ctx.lineTo(projOuter[b].x, projOuter[b].y);
      ctx.strokeStyle = rgba(NODE, 0.6);
      ctx.lineWidth = 1.3;
      ctx.shadowColor = rgba(NODE, 0.9);
      ctx.shadowBlur = 7;
      ctx.stroke();
    }
    ctx.shadowBlur = 0;
    const c = nodeColor(hoverNode);
    ctx.beginPath();
    ctx.arc(hp.x, hp.y, 5, 0, Math.PI * 2);
    ctx.fillStyle = rgba(c, 1);
    ctx.shadowColor = rgba(c, 1);
    ctx.shadowBlur = 18;
    ctx.fill();
    ctx.shadowBlur = 0;
    ctx.beginPath();
    ctx.arc(hp.x, hp.y, 8 + Math.sin(t * 6) * 2, 0, Math.PI * 2);
    ctx.strokeStyle = rgba(c, 0.6);
    ctx.lineWidth = 1.5;
    ctx.stroke();
  }

  // orbit particles
  for (const pt of particles) {
    const o = orbits[pt.orbit];
    pt.angle += dt * o.speed;
    const ox = cx + Math.cos(pt.angle + o.phase) * radius * o.rx;
    const oy = cy + Math.sin(pt.angle + o.phase) * radius * o.ry;
    ctx.beginPath();
    ctx.arc(ox, oy, pt.size, 0, Math.PI * 2);
    ctx.fillStyle = rgba(NODE, 0.45);
    ctx.shadowColor = rgba(NODE, 0.8);
    ctx.shadowBlur = 8;
    ctx.fill();
  }
  ctx.shadowBlur = 0;

  // ─── JARVIS reticle: concentric rings, tick gauge, rotating arcs, radar sweep ───
  const RR = radius * 1.5;
  ctx.lineWidth = 1;
  ctx.strokeStyle = rgba(NODE, 0.1);
  ctx.beginPath();
  ctx.arc(cx, cy, RR, 0, Math.PI * 2);
  ctx.stroke();
  ctx.save();
  ctx.setLineDash([5, 11]);
  ctx.lineDashOffset = -t * 26;
  ctx.strokeStyle = rgba(NODE, 0.16);
  ctx.beginPath();
  ctx.arc(cx, cy, RR * 1.14, 0, Math.PI * 2);
  ctx.stroke();
  ctx.setLineDash([3, 14]);
  ctx.lineDashOffset = t * 30;
  ctx.strokeStyle = rgba(GLOW, 0.16);
  ctx.beginPath();
  ctx.arc(cx, cy, RR * 0.72, 0, Math.PI * 2);
  ctx.stroke();
  ctx.restore();
  // tick gauge — batched into 2 strokes (minor + major) instead of 80
  const TK = 80;
  ctx.lineWidth = 0.7;
  ctx.strokeStyle = rgba(NODE, 0.12);
  ctx.beginPath();
  for (let i = 0; i < TK; i++) {
    if (i % 10 === 0) continue;
    const a = (i / TK) * Math.PI * 2 + t * 0.06;
    ctx.moveTo(cx + Math.cos(a) * RR * 0.92, cy + Math.sin(a) * RR * 0.92);
    ctx.lineTo(cx + Math.cos(a) * RR * 0.97, cy + Math.sin(a) * RR * 0.97);
  }
  ctx.stroke();
  ctx.lineWidth = 1.4;
  ctx.strokeStyle = rgba(NODE, 0.3);
  ctx.beginPath();
  for (let i = 0; i < TK; i += 10) {
    const a = (i / TK) * Math.PI * 2 + t * 0.06;
    ctx.moveTo(cx + Math.cos(a) * RR * 0.88, cy + Math.sin(a) * RR * 0.88);
    ctx.lineTo(cx + Math.cos(a) * RR * 0.97, cy + Math.sin(a) * RR * 0.97);
  }
  ctx.stroke();
  // rotating broken-arc ring + end nodes
  const AR = RR * 1.28;
  for (let k = 0; k < 3; k++) {
    const a0 = t * 0.25 + (k * Math.PI * 2) / 3;
    ctx.strokeStyle = rgba(NODE, 0.22);
    ctx.lineWidth = 1.6;
    ctx.beginPath();
    ctx.arc(cx, cy, AR, a0, a0 + 0.72);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(cx + Math.cos(a0) * AR, cy + Math.sin(a0) * AR, 2, 0, Math.PI * 2);
    ctx.fillStyle = rgba(NODE, 0.6);
    ctx.fill();
  }
  // radar sweep (fading trail)
  const sweep = t * 0.5;
  for (let s = 0; s < 16; s++) {
    const a = sweep - s * 0.028;
    ctx.strokeStyle = rgba(NODE, 0.1 * (1 - s / 16));
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + Math.cos(a) * RR * 0.95, cy + Math.sin(a) * RR * 0.95);
    ctx.stroke();
  }
  // screen-corner brackets (HUD frame)
  const bm = 26, bl = 22;
  ctx.strokeStyle = rgba(NODE, 0.28);
  ctx.lineWidth = 1.5;
  for (const [bx, by, sx, sy] of [[bm, bm, 1, 1], [W - bm, bm, -1, 1], [bm, H - bm, 1, -1], [W - bm, H - bm, -1, -1]] as const) {
    ctx.beginPath();
    ctx.moveTo(bx, by + sy * bl);
    ctx.lineTo(bx, by);
    ctx.lineTo(bx + sx * bl, by);
    ctx.stroke();
  }

  // ─── everything connected: tether each HUD panel to the brain (data flows in) ───
  for (const el of tetherEls) {
    const r = el.getBoundingClientRect();
    if (r.width < 4) continue;
    const ax = Math.max(r.left, Math.min(cx, r.right));
    const ay = Math.max(r.top, Math.min(cy, r.bottom));
    const ang = Math.atan2(ay - cy, ax - cx);
    const sx = cx + Math.cos(ang) * RR, sy = cy + Math.sin(ang) * RR;
    ctx.strokeStyle = rgba(NODE, 0.13);
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(sx, sy);
    ctx.lineTo(ax, ay);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(ax, ay, 2.5, 0, Math.PI * 2);
    ctx.fillStyle = rgba(NODE, 0.45);
    ctx.shadowColor = rgba(NODE, 0.7);
    ctx.shadowBlur = 6;
    ctx.fill();
    ctx.shadowBlur = 0;
    const pt = (t * 0.45 + ang) % 1;
    ctx.beginPath();
    ctx.arc(sx + (ax - sx) * pt, sy + (ay - sy) * pt, 1.8, 0, Math.PI * 2);
    ctx.fillStyle = rgba(NODE, 0.6 * (1 - pt));
    ctx.fill();
  }

  // answer shockwaves
  for (let i = ripples.length - 1; i >= 0; i--) {
    const rp = ripples[i];
    rp.t += dt * 0.65;
    if (rp.t >= 1) {
      ripples.splice(i, 1);
      continue;
    }
    const rr = radius * 0.3 + rp.t * radius * 2.3;
    ctx.beginPath();
    ctx.arc(cx, cy, rr, 0, Math.PI * 2);
    ctx.strokeStyle = rgba(NODE, 0.45 * (1 - rp.t));
    ctx.lineWidth = 2.4 * (1 - rp.t) + 0.4;
    ctx.stroke();
  }

  // question letters orbiting the net
  letterAlpha += ((thinking ? 1 : 0) - letterAlpha) * Math.min(1, dt * 3);
  if (!thinking && letterAlpha < 0.03) letters = [];
  if (letters.length) {
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    for (const L of letters) {
      const ang = L.a0 + t * L.speed;
      const ca = Math.cos(ang), sa = Math.sin(ang);
      const X = ca * L.orbR, Y = sa * L.orbR * Math.sin(L.tilt), Z = sa * L.orbR * Math.cos(L.tilt);
      const s = 340 / (340 + Z * radius * 0.55);
      const depth = (Z / L.orbR + 1) / 2;
      const a = letterAlpha * (0.2 + depth * 0.8);
      const sz = 12 + depth * 9;
      ctx.font = `700 ${sz}px -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif`;
      ctx.fillStyle = rgba(NODE, a);
      ctx.shadowColor = rgba(NODE, a);
      ctx.shadowBlur = 10 * depth;
      ctx.fillText(L.ch, cx + X * radius * s, cy + Y * radius * s);
    }
    ctx.shadowBlur = 0;
    ctx.textAlign = 'start';
    ctx.textBaseline = 'alphabetic';
  }

  ctx.globalCompositeOperation = 'source-over';

  // constellation labels — recent entry titles on the front-most nodes
  ctx.font = '600 11px -apple-system, BlinkMacSystemFont, sans-serif';
  ctx.textBaseline = 'middle';
  lastProj
    .map((p, i) => ({ p, i }))
    .filter((o) => nodeEntries[o.i] && (o.p.z + 1) / 2 > 0.84)
    .sort((a, b) => b.p.z - a.p.z)
    .slice(0, 5)
    .forEach(({ p, i }) => {
      const e = nodeEntries[i]!;
      const d = (p.z + 1) / 2;
      ctx.fillStyle = `rgba(226,232,240,${((d - 0.84) / 0.16) * 0.8})`;
      ctx.fillText(e.title.length > 26 ? e.title.slice(0, 25) + '…' : e.title, p.x + 9, p.y);
    });
  ctx.textBaseline = 'alphabetic';

  requestAnimationFrame(draw);
}

// click / hover a node → open its entry
function nodeAt(px: number, py: number): number {
  let best = -1, bd = 17 * 17;
  for (let i = 0; i < lastProj.length; i++) {
    const p = lastProj[i];
    if ((p.z + 1) / 2 < 0.4 || !nodeEntries[i]) continue;
    const dx = p.x - px, dy = p.y - py, d = dx * dx + dy * dy;
    if (d < bd) {
      bd = d;
      best = i;
    }
  }
  return best;
}
const tip = document.getElementById('ck-tip');
if (tip) tip.hidden = false; // visibility managed via the .show class + opacity fade
let tipHide = 0;
function hideTipSoon(): void {
  window.clearTimeout(tipHide);
  tipHide = window.setTimeout(() => tip?.classList.remove('show'), 450);
}
canvas.addEventListener('mousedown', (e) => {
  dragging = true;
  downX = lastX = e.clientX;
  downY = lastY = e.clientY;
});
window.addEventListener('mouseup', (e) => {
  if (!dragging) return;
  dragging = false;
  if (Math.hypot(e.clientX - downX, e.clientY - downY) < 5) {
    const i = nodeAt(e.clientX, e.clientY); // a click (not a drag) → open the entry
    if (i >= 0) window.vault.openFile(nodeEntries[i]!.file);
  }
});
canvas.addEventListener('mousemove', (e) => {
  if (dragging) {
    velY = (e.clientX - lastX) * 0.012; // drag spins the sphere (momentum decays in draw)
    velX = -(e.clientY - lastY) * 0.008;
    lastX = e.clientX;
    lastY = e.clientY;
  }
  const i = nodeAt(e.clientX, e.clientY);
  hoverNode = i;
  canvas.style.cursor = dragging ? 'grabbing' : i >= 0 ? 'pointer' : 'grab';
  if (!tip) return;
  if (i >= 0 && nodeEntries[i]) {
    window.clearTimeout(tipHide);
    const en = nodeEntries[i]!;
    tip.innerHTML = `<span class="type-badge t-${clsOf(en.type)}">${esc(en.type)}</span><span class="ck-tip-title">${esc(en.title)}</span>`;
    tip.style.left = `${Math.min(e.clientX + 14, W - 290)}px`;
    tip.style.top = `${e.clientY + 14}px`;
    tip.classList.add('show');
  } else if (tip.classList.contains('show')) {
    hideTipSoon(); // left the node → fade out after a grace delay
  }
});
canvas.addEventListener('mouseleave', () => {
  hoverNode = -1;
  hideTipSoon();
});

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
    el.innerHTML = `<span class="ck-big">${Math.round(to * (1 - Math.pow(1 - k, 3))).toLocaleString()}</span> notes`;
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
  void loadGraph();
  void loadTypes();
  void loadDoctor();
  void loadPending();
}

async function loadGraph(): Promise<void> {
  const entries = await window.vault.list();
  nodeEntries = outer.vertices.map((_, i) => {
    const e = entries[i];
    return e ? { type: e.type, file: e.file, title: e.title } : null;
  });
}

async function loadTypes(): Promise<void> {
  const entries = await window.vault.list();

  // ── activity stats: entries touched today / this week + a 7-day sparkline ──
  const midnight = new Date();
  midnight.setHours(0, 0, 0, 0);
  const startToday = midnight.getTime();
  const now = Date.now();
  const today = entries.filter((e) => e.mtimeMs >= startToday).length;
  const week = entries.filter((e) => e.mtimeMs >= now - 7 * 86400e3).length;
  const buckets = new Array(7).fill(0);
  for (const e of entries) {
    const d = new Date(e.mtimeMs);
    d.setHours(0, 0, 0, 0);
    const daysAgo = Math.round((startToday - d.getTime()) / 86400e3);
    if (daysAgo >= 0 && daysAgo < 7) buckets[6 - daysAgo]++;
  }
  const max = Math.max(1, ...buckets);
  const blocks = '▁▂▃▄▅▆▇█';
  const spark = buckets.map((b) => (b === 0 ? '·' : blocks[Math.min(7, Math.round((b / max) * 7))])).join('');
  const act = document.getElementById('ck-activity');
  if (act) {
    act.innerHTML =
      `<span class="ck-act-num">+${today}</span> today` +
      `<span class="ck-act-sep">·</span><span class="ck-act-num">+${week}</span> this week` +
      `<span class="ck-act-spark" title="entries per day, last 7 days (today right)">${spark}</span>`;
  }

  const el = document.getElementById('ck-types');
  if (!el) return;
  const counts: Record<string, number> = {};
  for (const e of entries) counts[e.type] = (counts[e.type] || 0) + 1;
  el.innerHTML = Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
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

let busy = false;
function setBusy(b: boolean): void {
  busy = b;
  targetEnergy = b ? 1 : thinking ? 1 : 0.35;
  const u = document.getElementById('ck-update') as HTMLButtonElement | null;
  if (u) {
    u.disabled = b;
    u.textContent = b ? 'Working…' : 'Update knowledge';
  }
}

async function loadPending(): Promise<void> {
  const m = await window.vault.menu();
  const tel = document.getElementById('ck-telemetry');
  if (tel) {
    const st = (m?.status ?? {}) as { articles?: number; last_compile_ago?: string; ollama_reachable?: boolean };
    tel.innerHTML = [
      st.articles != null ? `NOTES ${st.articles}` : '',
      st.last_compile_ago ? `COMPILED ${esc(st.last_compile_ago)} AGO` : '',
      `OLLAMA ${st.ollama_reachable ? 'ONLINE' : 'OFFLINE'}`,
    ]
      .filter(Boolean)
      .map((s) => `<span>${s}</span>`)
      .join('<span class="ck-tel-sep">//</span>');
  }
  const el = document.getElementById('ck-pending-list');
  if (!el) return;
  const items = (m?.suggestions ?? []).slice(0, 5);
  el.innerHTML = '';
  if (items.length === 0) {
    el.innerHTML = `<div class="ck-empty">Nothing pending 🎉</div>`;
    return;
  }
  for (const s of items) {
    const row = document.createElement('div');
    row.className = 'ck-pending-row';
    row.innerHTML = `<span class="ck-pending-label" title="${esc(s.label)}">${esc(friendlyPending(s))}</span>`;
    const b = document.createElement('button');
    b.className = 'ck-run';
    b.textContent = 'Run';
    b.title = 'Do this now — runs in the background, usually under a minute';
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
setInterval(() => {
  void window.vault.runStatus().then((s) => {
    if (!busy && !thinking) targetEnergy = s.running ? 1 : 0.35;
  });
}, 1500);

// ── ask (with copy + close on the answer) ──
let asking = false;
async function ask(): Promise<void> {
  const input = document.getElementById('ck-input') as HTMLInputElement | null;
  const answer = document.getElementById('ck-answer');
  const btn = document.getElementById('ck-ask-btn') as HTMLButtonElement | null;
  if (!input || !answer || asking) return;
  const q = input.value.trim();
  if (!q) return;
  asking = true;
  igniteFromAsk(q); // letters orbit the net + the sphere ramps up
  if (btn) btn.disabled = true;
  answer.hidden = false;
  answer.className = 'ck-answer thinking';
  answer.textContent = 'Thinking…';
  try {
    const res = await window.vault.query(q);
    if (res.ok) {
      const html = marked.parse(
        res.answer.replace(/\[\[([^\]]+)\]\]/g, (_m, p: string) => esc((p.split('|')[0].split('#')[0].split('/').pop() || p).trim())),
        { breaks: true, async: false },
      ) as string;
      answer.className = 'ck-answer';
      answer.innerHTML = `<div class="ck-tools"><button class="ck-icon copy" title="Copy">${ICO_COPY}</button><button class="ck-icon close" title="Close">${ICO_X}</button></div><div class="md">${html}</div>`;
      const copyBtn = answer.querySelector('.copy') as HTMLButtonElement | null;
      copyBtn?.addEventListener('click', () => {
        void navigator.clipboard.writeText(res.answer).then(() => {
          copyBtn.innerHTML = ICO_CHECK;
          copyBtn.classList.add('done');
          window.setTimeout(() => {
            copyBtn.innerHTML = ICO_COPY;
            copyBtn.classList.remove('done');
          }, 1500);
        });
      });
      answer.querySelector('.close')?.addEventListener('click', () => {
        answer.hidden = true;
        answer.innerHTML = '';
      });
      ripples.push({ t: 0 }); // the brain responds — shockwave through the net
    } else {
      answer.className = 'ck-answer err';
      answer.textContent = res.answer || 'No answer.';
    }
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
