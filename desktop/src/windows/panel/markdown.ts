// The Ask answer: engine markdown → HTML, with Obsidian wikilinks turned into chips that carry
// the vault-relative path in `data-file` (the Ask component delegates clicks on `.wl` to
// window.vault.openFile).

import { marked } from 'marked';

const ESCAPES: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' };
const escapeHtml = (s: string): string => s.replace(/[&<>"]/g, (c) => ESCAPES[c]);

export function renderAnswer(markdown: string): string {
  const withChips = markdown.replace(/\[\[([^\]]+)\]\]/g, (_match, inner: string) => {
    const [target, alias] = inner.split('|');
    const file = target.split('#')[0].trim();
    const label = (alias ?? file.split('/').pop() ?? file).trim();
    return `<button class="wl" data-file="${escapeHtml(file)}">${escapeHtml(label)}</button>`;
  });
  return marked.parse(withChips, { breaks: true, async: false }) as string;
}
