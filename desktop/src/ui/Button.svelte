<script lang="ts">
  import type { Snippet } from 'svelte';

  interface Props {
    variant?: 'primary' | 'secondary' | 'quiet';
    size?: 's' | 'm';
    disabled?: boolean;
    title?: string;
    type?: 'button' | 'submit';
    onclick?: (event: MouseEvent) => void;
    children: Snippet;
  }

  let { variant = 'secondary', size = 'm', disabled = false, title, type = 'button', onclick, children }: Props = $props();
</script>

<button class="btn {variant} {size}" {type} {disabled} {title} {onclick}>
  {@render children()}
</button>

<style>
  .btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: var(--space-1);
    height: var(--control-h);
    padding: 0 var(--space-3);
    border: 1px solid transparent;
    border-radius: var(--radius-s);
    font-size: var(--fs-m);
    font-weight: 500;
    white-space: nowrap;
    cursor: default;
    transition:
      background-color var(--dur-fast) var(--ease-out),
      transform var(--dur-fast) var(--ease-out);
  }
  .btn.s {
    height: var(--control-h-s);
    padding: 0 var(--space-2);
    font-size: var(--fs-s);
  }
  .btn:active:not(:disabled) {
    transform: scale(0.97);
  }
  .btn:disabled {
    color: var(--text-disabled);
    cursor: default;
  }

  .primary {
    background: var(--accent);
    color: var(--text-on-accent);
    font-weight: 600;
  }
  .primary:hover:not(:disabled) {
    background: var(--accent-hover);
  }
  .primary:disabled {
    background: var(--bg-sunken);
  }

  .secondary {
    background: var(--bg-sunken);
    border-color: var(--line);
  }
  .secondary:hover:not(:disabled) {
    background: var(--bg-hover);
  }

  .quiet {
    background: transparent;
    color: var(--text-muted);
  }
  .quiet:hover:not(:disabled) {
    background: var(--bg-hover);
    color: var(--text);
  }
</style>
