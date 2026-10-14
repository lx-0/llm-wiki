<script lang="ts">
  import Button from '../../ui/Button.svelte';
  import { icon } from '../../ui/icons';
  import { renderAnswer } from './markdown';
  import { ask } from './store.svelte';

  let question = $state('');
  let asking = $state(false);
  let answer = $state<{ ok: boolean; text: string } | null>(null);
  let copied = $state(false);

  async function submit(): Promise<void> {
    const q = question.trim();
    if (!q || asking) return;
    asking = true;
    try {
      const res = await ask(q);
      answer = { ok: res.ok, text: res.answer };
    } catch {
      answer = { ok: false, text: 'Something went wrong.' };
    } finally {
      asking = false;
    }
  }

  /** Wikilink chips are rendered from markdown ({@html}), so the open-in-Obsidian click is
   *  delegated from the answer container by an action instead of a template handler. */
  function chipLinks(node: HTMLElement): { destroy(): void } {
    const onClick = (event: MouseEvent): void => {
      const chip = (event.target as HTMLElement).closest('.wl') as HTMLElement | null;
      if (chip?.dataset.file) window.vault.openFile(chip.dataset.file);
    };
    node.addEventListener('click', onClick);
    return { destroy: () => node.removeEventListener('click', onClick) };
  }

  async function copy(): Promise<void> {
    if (!answer) return;
    await navigator.clipboard.writeText(answer.text);
    copied = true;
    window.setTimeout(() => (copied = false), 1500);
  }
</script>

<div class="ask">
  <form class="bar" onsubmit={(e) => { e.preventDefault(); void submit(); }}>
    <input
      id="ask-input"
      type="text"
      placeholder="Ask your wiki anything…"
      autocomplete="off"
      spellcheck="false"
      bind:value={question}
      onkeydown={(e) => { if (e.key === 'Enter') { e.preventDefault(); void submit(); } }}
    />
    <Button variant="primary" type="submit" disabled={asking}>{asking ? '…' : 'Ask'}</Button>
  </form>

  {#if asking}
    <div class="answer thinking">Thinking…</div>
  {:else if answer}
    <div class="answer card" class:err={!answer.ok}>
      <div class="tools">
        <Button size="s" variant="quiet" title="Copy" onclick={() => void copy()}>{@html copied ? icon.check(13) : icon.copy(13)}</Button>
        <Button size="s" variant="quiet" title="Clear" onclick={() => (answer = null)}>{@html icon.close(13)}</Button>
      </div>
      <div class="md" use:chipLinks>{@html renderAnswer(answer.text)}</div>
    </div>
  {/if}
</div>

<style>
  .ask {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .bar {
    display: flex;
    gap: var(--space-2);
  }
  input {
    flex: 1;
    min-width: 0;
    height: 36px;
    padding: 0 var(--space-3);
    border: 1px solid var(--line);
    border-radius: var(--radius-m);
    background: var(--bg-elevated);
    font-size: var(--fs-l);
    outline: none;
  }
  input::placeholder {
    color: var(--text-faint);
  }
  input:focus-visible {
    border-color: var(--accent);
    box-shadow: var(--focus);
  }
  .thinking {
    padding: var(--space-2) var(--space-3);
    color: var(--text-muted);
    font-size: var(--fs-s);
  }
  .answer.card {
    position: relative;
    padding: var(--space-3);
    user-select: text;
  }
  .answer.err {
    border-color: var(--danger);
  }
  .tools {
    position: absolute;
    top: var(--space-1);
    right: var(--space-1);
    display: flex;
  }
  .md {
    padding-right: 56px;
    font-size: var(--fs-m);
    line-height: 1.45;
  }
  .md :global(p) {
    margin: 0 0 var(--space-2);
  }
  .md :global(p:last-child) {
    margin-bottom: 0;
  }
  .md :global(.wl) {
    display: inline;
    padding: 0 3px;
    border: none;
    border-radius: 4px;
    background: var(--accent-soft);
    color: var(--accent);
    font: inherit;
    font-weight: 500;
  }
  .md :global(.wl:hover) {
    text-decoration: underline;
  }
</style>
