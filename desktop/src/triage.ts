// Triage window — the per-item review surface for the intent inbox. Each captured
// record is a card with a decision (Accept/Keep · Dismiss); the action runs the fast
// non-interactive `wiki triage <action> <stem>` and the list refreshes. This is the
// UX pattern for engine commands that need a human decision, not just a run.
import './index.css';

interface Rec {
  stem: string;
  type: string;
  status: string;
  summary: string;
  source: string;
  date: string;
  confidence: string;
}

let showAll = false;
let records: Rec[] = [];
const busy = new Set<string>();
const errors = new Map<string, string>();

function esc(s: string): string {
  return s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c] as string);
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
  for (const r of records) {
    const card = document.createElement('div');
    card.className = 'triage-card' + (r.status !== 'pending' ? ' resolved' : '');
    const cls = ['task', 'idea', 'note'].includes(r.type) ? r.type : 'note';
    const meta = [r.date, r.confidence && `${r.confidence} confidence`].filter(Boolean).join(' · ');
    card.innerHTML = `
      <div class="triage-card-top">
        <span class="type-badge t-${cls}">${esc(r.type)}</span>
        ${r.status !== 'pending' ? `<span class="triage-status">${esc(r.status)}</span>` : ''}
        <span class="triage-date">${esc(meta)}</span>
      </div>
      <div class="triage-summary">${esc(r.summary)}</div>`;
    const err = errors.get(r.stem);
    if (err) {
      const e = document.createElement('div');
      e.className = 'triage-error';
      e.textContent = err;
      card.appendChild(e);
    }
    if (r.status === 'pending') {
      const actions = document.createElement('div');
      actions.className = 'triage-actions';
      if (busy.has(r.stem)) {
        actions.innerHTML = `<span class="triage-working">Working…</span>`;
      } else {
        const acc = document.createElement('button');
        acc.className = 'triage-accept';
        acc.textContent = r.type === 'task' ? 'Accept → task' : 'Keep';
        acc.title = r.type === 'task' ? 'Move to tasks/ and list in todo.md' : 'File in place (status: accepted)';
        acc.addEventListener('click', () => void act(r.stem, 'accept'));
        const dis = document.createElement('button');
        dis.className = 'triage-dismiss';
        dis.textContent = 'Dismiss';
        dis.title = 'Drop as noise (status: dismissed)';
        dis.addEventListener('click', () => void act(r.stem, 'dismiss'));
        actions.append(acc, dis);
      }
      card.appendChild(actions);
    }
    list.appendChild(card);
  }
}

async function act(stem: string, action: 'accept' | 'dismiss'): Promise<void> {
  if (busy.has(stem)) return;
  errors.delete(stem);
  busy.add(stem);
  render();
  const res = await window.vault.triageAction(stem, action);
  busy.delete(stem);
  if (res.ok) {
    await load(); // record changed status → drops out of the pending list
  } else {
    errors.set(stem, res.message || 'Action failed.');
    render();
  }
}

document.getElementById('triage-all')?.addEventListener('change', (e) => {
  showAll = (e.target as HTMLInputElement).checked;
  void load();
});
void load();
