<script lang="ts">
  import { onMount } from 'svelte';
  import Button from '../../ui/Button.svelte';
  import Switch from '../../ui/Switch.svelte';
  import { captureLabel, fileAccessLabel } from './labels';

  type VaultStatus = Awaited<ReturnType<typeof window.vault.status>>;
  type Listener = Awaited<ReturnType<typeof window.listeners.status>>[number];

  let vault = $state<VaultStatus>(null);
  let listener = $state<Listener | null>(null);
  let loginItem = $state(false);
  let loaded = $state(false);

  const shortPath = $derived(vault ? vault.path.replace(/^\/Users\/[^/]+/, '~') : '');
  const access = $derived(fileAccessLabel(vault));
  const capture = $derived(captureLabel(listener));

  onMount(async () => {
    const [status, listeners, login] = await Promise.all([
      window.vault.status(),
      window.listeners.status().catch(() => []),
      window.app.getLoginItem(),
    ]);
    vault = status;
    listener = listeners[0] ?? null;
    loginItem = login;
    loaded = true;
  });

  async function setLogin(open: boolean): Promise<void> {
    loginItem = await window.app.setLoginItem(open);
  }
</script>

<main class="settings">
  <h1>Settings</h1>

  <section class="card">
    <div class="row">
      <div class="grow">
        <div class="label">
          {#if vault}
            <strong>{vault.name}</strong> <span class="muted num">· {vault.articleCount.toLocaleString()} notes</span>
          {:else if loaded}
            No library yet
          {:else}
            …
          {/if}
        </div>
        {#if vault}
          <div class="path" title={vault.path}>{shortPath}</div>
        {/if}
      </div>
      {#if vault}
        <Button size="s" onclick={() => void window.vault.openInObsidian()}>Open in Obsidian</Button>
      {/if}
    </div>
  </section>

  <section class="card">
    <div class="row">
      <span class="grow">Start at login</span>
      <Switch bind:checked={loginItem} label="Start at login" onchange={(v) => void setLogin(v)} />
    </div>
    <div class="row">
      <span class="grow">File access</span>
      <span class="value" class:warn={vault && !vault.accessible}>{loaded ? access : '…'}</span>
      {#if vault && !vault.accessible}
        <Button size="s" onclick={() => window.vault.openFullDiskAccess()}>Open System Settings</Button>
      {/if}
    </div>
    <div class="row">
      <span class="grow">Screen &amp; audio capture</span>
      <span class="value" class:ok={listener?.running}>{loaded ? capture : '…'}</span>
    </div>
  </section>
</main>

<style>
  .settings {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    padding: var(--space-4) var(--space-4) var(--space-5);
  }
  h1 {
    font-size: var(--fs-l);
    font-weight: 600;
    margin-bottom: var(--space-1);
  }
  .grow {
    flex: 1;
    min-width: 0;
  }
  .label {
    font-size: var(--fs-m);
  }
  .muted {
    color: var(--text-muted);
  }
  .path {
    margin-top: 2px;
    font-family: var(--font-mono);
    font-size: var(--fs-xs);
    color: var(--text-faint);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .value {
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
  }
  .value.ok {
    color: var(--ok);
  }
  .value.warn {
    color: var(--warn);
  }
</style>
