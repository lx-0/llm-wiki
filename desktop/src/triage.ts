// Triage window — per-item intent-inbox review, reworked from synthetic-user feedback:
// grouped by type with batch actions (clear the low-stakes bulk in one gesture),
// type-coloured hierarchy (notes recede, tasks lead), confidence as a colour dot with
// uncertain items sorted to the top, plain consistent Keep/Dismiss, and the jargon
// rationale line dropped. Records read directly; actions run `wiki triage <verb> <stem>`.
import './index.css';

interface Rec {
  stem: string;
  type: string;
  status: string;
  summary: string;
  source: string;
  detail: string;
  date: string;
  confidence: string;
}

const TYPES = [
  { key: 'task', label: 'Tasks', color: '#5fd3e0', hint: 'Keep → becomes a to-do' },
  { key: 'idea', label: 'Ideas', color: '#e8b94c', hint: 'Keep → filed for reference' },
  { key: 'note', label: 'Notes', color: '#b3a7f0', hint: 'Keep → filed for reference' },
];
const CONF_COLOR: Record<string, string> = { high: '#34d399', medium: '#e8b94c', low: '#fb7185' };
const CONF_RANK: Record<string, number> = { low: 0, medium: 1, high: 2 };
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

let showAll = false;
let records: Rec[] = [];
const busy = new Set<string>();
const errors = new Map<string, string>();
const batching = new Map<string, { done: number; total: number }>();

function esc(s: string): string {
  return s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c] as string);
}
function srcSub(src: string): string {
  const p = src.split('/');
  return p.length >= 2 ? p[p.length - 2] : p[0] || '';
}
function fmtDate(d: string): string {
  const [, m, day] = d.split('-');
  const mon = MONTHS[Number(m) - 1];
  return mon ? `${Number(day)} ${mon}` : d;
}

async function load(): Promise<void> {
  records = await window.vault.triage(showAll);
  render();
}

function render(): void {
  const list = document.getElementById('triage-list');
  const count = document.getElementById('triage-count');
  if (!list || !count) return;
  const pending = records.filter((r) => r.status === 'pending').length;
  count.textContent = pending ? String(pending) : '';

  if (records.length === 0) {
    list.innerHTML = `<div class="triage-empty"><div class="triage-empty-ic">✓</div><p>Inbox clear — nothing to triage.</p></div>`;
    return;
  }
  list.innerHTML = '';
  const known = new Set(TYPES.map((t) => t.key));
  const groups = [...TYPES, { key: 'other', label: 'Other', color: '#93a4bd', hint: '' }];
  for (const t of groups) {
    const items = records
      .filter((r) => (t.key === 'other' ? !known.has(r.type) : r.type === t.key))
      .sort((a, b) => (CONF_RANK[a.confidence] ?? 1) - (CONF_RANK[b.confidence] ?? 1) || b.stem.localeCompare(a.stem));
    if (items.length) list.appendChild(renderGroup(t, items));
  }
}

function renderGroup(t: { key: string; label: string; color: string; hint: string }, items: Rec[]): HTMLElement {
  const pendingItems = items.filter((r) => r.status === 'pending');
  const sec = document.createElement('section');
  sec.className = 'triage-group' + (t.key === 'note' ? ' muted' : '');

  const head = document.createElement('div');
  head.className = 'triage-group-head';
  head.innerHTML = `<span class="triage-group-label" style="color:${t.color}"><span class="triage-group-dot" style="background:${t.color}"></span>${t.label}</span><span class="triage-group-count">${pendingItems.length}</span>`;
  const batch = batching.get(t.key);
  if (batch) {
    const p = document.createElement('span');
    p.className = 'triage-batch-prog';
    p.textContent = `working ${batch.done}/${batch.total}…`;
    head.appendChild(p);
  } else if (pendingItems.length > 1) {
    const wrap = document.createElement('div');
    wrap.className = 'triage-batch';
    const keep = document.createElement('button');
    keep.className = 'triage-batch-keep';
    keep.textContent = 'Keep all';
    keep.addEventListener('click', () => void batchAct(t.key, 'accept'));
    const dis = document.createElement('button');
    dis.className = 'triage-batch-dismiss';
    dis.textContent = 'Dismiss all';
    dis.addEventListener('click', () => void batchAct(t.key, 'dismiss'));
    wrap.append(keep, dis);
    head.appendChild(wrap);
  }
  sec.appendChild(head);
  if (t.hint) {
    const h = document.createElement('p');
    h.className = 'triage-group-hint';
    h.textContent = t.hint;
    sec.appendChild(h);
  }
  for (const r of items) sec.appendChild(renderRow(r, t.color));
  return sec;
}

function renderRow(r: Rec, accent: string): HTMLElement {
  const row = document.createElement('div');
  const lc = r.confidence === 'low';
  row.className = 'triage-row' + (lc ? ' lc' : '') + (r.status !== 'pending' ? ' resolved' : '');
  row.style.setProperty('--accent', accent);
  const meta = [r.source && `from ${srcSub(r.source)}`, fmtDate(r.date), r.status !== 'pending' ? r.status : '']
    .filter(Boolean)
    .join(' · ');
  row.innerHTML = `
    <div class="triage-main">
      <div class="triage-summary">${esc(r.summary)}</div>
      <div class="triage-meta${r.source ? ' clickable' : ''}">${esc(meta)}</div>
    </div>`;
  if (r.source) {
    const m = row.querySelector('.triage-meta') as HTMLElement;
    m.title = `Open ${r.source} in Obsidian`;
    m.addEventListener('click', () => window.vault.openFile(r.source));
  }
  const err = errors.get(r.stem);
  if (err) {
    const e = document.createElement('div');
    e.className = 'triage-error';
    e.textContent = err;
    row.querySelector('.triage-main')?.appendChild(e);
  }
  if (r.status === 'pending') {
    // "unsure" only on the low-confidence items (the ones that actually need a look),
    // so the label IS its own legend; hover shows why. No colour-dot on every row.
    if (lc) {
      const u = document.createElement('span');
      u.className = 'triage-unsure';
      u.textContent = 'unsure';
      u.title = r.detail ? `Low confidence — ${r.detail}` : 'Low confidence — worth a look before keeping';
      row.appendChild(u);
    }
    const actions = document.createElement('div');
    actions.className = 'triage-row-actions';
    if (busy.has(r.stem) || batching.has(r.type)) {
      actions.innerHTML = `<span class="triage-working">…</span>`;
    } else {
      const keep = document.createElement('button');
      keep.className = 'triage-accept';
      keep.textContent = r.type === 'task' ? 'Keep → to-do' : 'Keep';
      keep.title = r.type === 'task' ? 'Keep → becomes a to-do in todo.md' : 'Keep → filed for reference';
      keep.addEventListener('click', () => void act(r.stem, 'accept'));
      const dis = document.createElement('button');
      dis.className = 'triage-dismiss';
      dis.textContent = 'Dismiss';
      dis.title = 'Drop as noise';
      dis.addEventListener('click', () => void act(r.stem, 'dismiss'));
      actions.append(keep, dis);
    }
    row.appendChild(actions);
  }
  return row;
}

async function act(stem: string, action: 'accept' | 'dismiss'): Promise<void> {
  if (busy.has(stem)) return;
  errors.delete(stem);
  busy.add(stem);
  render();
  const res = await window.vault.triageAction(stem, action);
  busy.delete(stem);
  if (res.ok) {
    await load();
  } else {
    errors.set(stem, res.message || 'Action failed.');
    render();
  }
}

async function batchAct(type: string, action: 'accept' | 'dismiss'): Promise<void> {
  if (batching.has(type)) return;
  const stems = records.filter((r) => r.type === type && r.status === 'pending').map((r) => r.stem);
  if (!stems.length) return;
  const verb = action === 'accept' ? 'Keep' : 'Dismiss';
  if (!window.confirm(`${verb} all ${stems.length} ${type}${stems.length === 1 ? '' : 's'}?`)) return;
  batching.set(type, { done: 0, total: stems.length });
  render();
  let i = 0;
  const worker = async (): Promise<void> => {
    while (i < stems.length) {
      const stem = stems[i++];
      await window.vault.triageAction(stem, action);
      const b = batching.get(type);
      if (b) {
        b.done++;
        render();
      }
    }
  };
  await Promise.all([worker(), worker(), worker()]); // small pool — gentle on uv spawns
  batching.delete(type);
  await load();
}

document.getElementById('triage-all')?.addEventListener('change', (e) => {
  showAll = (e.target as HTMLInputElement).checked;
  void load();
});
void load();
