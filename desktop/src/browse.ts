// Browse window — a searchable, type-filterable list of every knowledge entry.
// Same preload, so window.vault.list() / openFile() are available.
import './index.css';

type Entry = { title: string; file: string; type: string; mtimeMs: number };

const MAX_ROWS = 400; // cap the DOM; search narrows it
let all: Entry[] = [];
let typeFilter = '';

const input = document.getElementById('browse-input') as HTMLInputElement | null;
const listEl = document.getElementById('browse-list');
const countEl = document.getElementById('browse-count');
const filtersEl = document.getElementById('browse-filters');

function escapeHtml(s: string): string {
  return s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c] as string);
}

function fmtAgo(ms: number): string {
  const s = Math.max(0, (Date.now() - ms) / 1000);
  if (s < 90) return 'just now';
  const m = s / 60;
  if (m < 90) return `${Math.round(m)}m`;
  const h = m / 60;
  if (h < 36) return `${Math.round(h)}h`;
  return `${Math.round(h / 24)}d`;
}

function renderFilters(): void {
  if (!filtersEl) return;
  const types = Array.from(new Set(all.map((e) => e.type))).sort();
  const chip = (label: string, value: string) =>
    `<button class="chip ${typeFilter === value ? 'on' : ''}" data-type="${escapeHtml(value)}">${escapeHtml(label)}</button>`;
  filtersEl.innerHTML = chip('All', '') + types.map((t) => chip(t, t)).join('');
  filtersEl.querySelectorAll('.chip').forEach((b) =>
    b.addEventListener('click', () => {
      typeFilter = (b as HTMLElement).dataset.type || '';
      renderFilters();
      render();
    }),
  );
}

function render(): void {
  if (!listEl) return;
  const q = (input?.value || '').trim().toLowerCase();
  const filtered = all.filter(
    (e) =>
      (!typeFilter || e.type === typeFilter) &&
      (!q || e.title.toLowerCase().includes(q) || e.file.toLowerCase().includes(q)),
  );
  if (countEl) countEl.textContent = `${filtered.length}`;
  listEl.innerHTML = '';
  for (const e of filtered.slice(0, MAX_ROWS)) {
    const cls = e.type.replace(/[^a-zA-Z0-9]/g, '').toLowerCase() || 'note';
    const row = document.createElement('button');
    row.className = 'browse-row';
    row.title = 'Open in Obsidian';
    row.innerHTML =
      `<span class="type-badge t-${cls}">${escapeHtml(e.type)}</span>` +
      `<span class="browse-title">${escapeHtml(e.title)}</span>` +
      `<span class="browse-ago">${fmtAgo(e.mtimeMs)}</span>`;
    row.addEventListener('click', () => window.vault.openFile(e.file));
    listEl.appendChild(row);
  }
  if (filtered.length > MAX_ROWS) {
    const more = document.createElement('div');
    more.className = 'browse-more';
    more.textContent = `Showing the first ${MAX_ROWS} of ${filtered.length} — refine your search.`;
    listEl.appendChild(more);
  }
}

input?.addEventListener('input', render);

void window.vault.list().then((entries) => {
  all = entries as Entry[];
  renderFilters();
  render();
});
