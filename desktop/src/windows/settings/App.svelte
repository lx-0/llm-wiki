<script lang="ts">
  import { onMount } from 'svelte';
  import Button from '../../ui/Button.svelte';
  import Switch from '../../ui/Switch.svelte';
  import { captureLabel, fileAccessLabel } from './labels';

  type VaultStatus = Awaited<ReturnType<typeof window.vault.status>>;
  type Listener = Awaited<ReturnType<typeof window.listeners.status>>[number];

  let vault = $state<VaultStatus>(null);
  let listener = $state<Listener | null>(null);
  let captureOn = $state(false);
  let loginItem = $state(false);
  let loaded = $state(false);

  const shortPath = $derived(vault ? vault.path.replace(/^\/Users\/[^/]+/, '~') : '');
  const access = $derived(fileAccessLabel(vault));
  const capture = $derived(captureLabel(listener));

  async function loadListener(): Promise<void> {
    const listeners = await window.listeners.status().catch(() => [] as Listener[]);
    listener = listeners[0] ?? null;
    captureOn = listener?.running ?? false;
  }

  onMount(async () => {
    const [status, login] = await Promise.all([window.vault.status(), window.app.getLoginItem()]);
    vault = status;
    loginItem = login;
    await loadListener();
    loaded = true;
  });

  async function setLogin(open: boolean): Promise<void> {
    loginItem = await window.app.setLoginItem(open);
  }

  /** The same switch the welcome screen has — the off switch lives here as well as in the panel. */
  async function setCapture(on: boolean): Promise<void> {
    if (!listener) return;
    const res = await window.listeners.control(listener.id, on ? 'start' : 'stop');
    if (!res.ok) {
      captureOn = !on;
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 1500)); // let launchd flip state
    await loadListener();
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
          <div class="path" title={vault.path}>Your library is the Obsidian vault at {shortPath}</div>
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
      <span class="grow">
        Screen &amp; audio capture
        <span class="sub">{loaded ? capture : '…'}</span>
      </span>
      {#if listener}
        <Switch bind:checked={captureOn} label="Screen & audio capture" onchange={(v) => void setCapture(v)} />
      {/if}
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
    font-size: var(--fs-xs);
    color: var(--text-muted);
    overflow-wrap: anywhere;
  }
  .sub {
    display: block;
    margin-top: 2px;
    font-size: var(--fs-xs);
    color: var(--text-muted);
  }
  .value {
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
  }
  .value.warn {
    color: var(--warn);
  }
</style>
