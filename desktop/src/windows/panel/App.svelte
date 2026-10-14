<script lang="ts">
  import { onMount } from 'svelte';
  import Ask from './Ask.svelte';
  import Header from './Header.svelte';
  import StatusStrip from './StatusStrip.svelte';
  import { connect } from './store.svelte';

  onMount(() => {
    const disconnect = connect();
    // Auto-fit the popover to its content — main clamps to PANEL_MAX_H.
    const fit = () => window.panel.resize(document.documentElement.scrollHeight);
    const observer = new ResizeObserver(fit);
    observer.observe(document.body);
    fit();
    return () => {
      disconnect();
      observer.disconnect();
    };
  });
</script>

<main class="panel-root">
  <Header />
  <Ask />
  <StatusStrip />
</main>

<style>
  .panel-root {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    padding: var(--space-3) var(--space-3) var(--space-3);
  }
</style>
