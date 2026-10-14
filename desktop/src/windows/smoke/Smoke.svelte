<script lang="ts">
  // Pipeline smoke test for the Svelte scaffold (M032-S01-T05): proves TS inside a
  // component, a $state rune, and preload access from Svelte, end-to-end through the
  // harness. Replaced by the real windows in S03.
  let label = $state('…');

  $effect(() => {
    void window.vault.status().then((v) => {
      label = v ? `${v.name} · ${v.articleCount.toLocaleString()} notes` : 'no library';
    });
  });
</script>

<main class="smoke">
  <h1>Svelte scaffold</h1>
  <p>{label}</p>
</main>

<style>
  .smoke {
    font-family: -apple-system, BlinkMacSystemFont, sans-serif;
    padding: 24px;
  }
</style>
