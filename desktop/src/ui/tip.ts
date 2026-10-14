// One tooltip per window — a Svelte action: `use:tip={text}` shows the text near the element on
// hover and on keyboard focus. The text is also the element's aria-label, so the tooltip
// enhances and never gates. Styled by `.tip` in tokens.css.

import type { Action } from 'svelte/action';

let box: HTMLDivElement | null = null;

function ensureBox(): HTMLDivElement {
  if (!box) {
    box = document.createElement('div');
    box.className = 'tip';
    box.setAttribute('role', 'tooltip');
    box.hidden = true;
    document.body.appendChild(box);
  }
  return box;
}

export const tip: Action<Element, string> = (node, text) => {
  let current = text;
  node.setAttribute('aria-label', current);

  const show = (): void => {
    const el = ensureBox();
    el.textContent = current;
    el.hidden = false;
    const r = node.getBoundingClientRect();
    const x = Math.max(
      4,
      Math.min(r.left + r.width / 2 - el.offsetWidth / 2, window.innerWidth - el.offsetWidth - 4),
    );
    const above = r.top - el.offsetHeight - 6;
    const y = above >= 4 ? above : r.bottom + 6;
    el.style.transform = `translate(${Math.round(x)}px, ${Math.round(y)}px)`;
  };
  const hide = (): void => {
    if (box) box.hidden = true;
  };
  const onKey = (event: Event): void => {
    if ((event as KeyboardEvent).key === 'Escape') hide();
  };

  node.addEventListener('pointerenter', show);
  node.addEventListener('pointerleave', hide);
  node.addEventListener('focus', show);
  node.addEventListener('blur', hide);
  node.addEventListener('keydown', onKey);

  return {
    update(next: string) {
      current = next;
      node.setAttribute('aria-label', next);
      if (box && !box.hidden) show();
    },
    destroy() {
      node.removeEventListener('pointerenter', show);
      node.removeEventListener('pointerleave', hide);
      node.removeEventListener('focus', show);
      node.removeEventListener('blur', hide);
      node.removeEventListener('keydown', onKey);
      hide();
    },
  };
};
