<script lang="ts">
  import { onMount } from 'svelte';
  import Button from '../../ui/Button.svelte';
  import { icon } from '../../ui/icons';
  import Switch from '../../ui/Switch.svelte';

  type VaultStatus = Awaited<ReturnType<typeof window.vault.status>>;
  type Listener = Awaited<ReturnType<typeof window.listeners.status>>[number];

  let vault = $state<VaultStatus>(null);
  let listener = $state<Listener | null>(null);
  let capture = $state(false);
  let loginItem = $state(false);
  let loaded = $state(false);

  async function loadVault(): Promise<void> {
    vault = await window.vault.status();
  }

  onMount(async () => {
    const [status, listeners, login] = await Promise.all([
      window.vault.status(),
      window.listeners.status().catch(() => []),
      window.app.getLoginItem(),
    ]);
    vault = status;
    listener = listeners[0] ?? null;
    capture = listener?.running ?? false;
    loginItem = login;
    loaded = true;
  });

  async function setCapture(on: boolean): Promise<void> {
    if (!listener) return;
    const res = await window.listeners.control(listener.id, on ? 'start' : 'stop');
    if (!res.ok) capture = !on; // revert on failure
  }

  async function setLogin(open: boolean): Promise<void> {
    loginItem = await window.app.setLoginItem(open);
  }
</script>

<main class="onboarding">
  <header class="hero">
    <span class="logo">{@html icon.logo(40)}</span>
    <h1>Welcome to llm-wiki</h1>
    <p class="lede">Your notes, mail, meetings and screenshots become one private library you can ask.</p>
  </header>

  <section class="card">
    <div class="row">
      <span class="grow">Your library</span>
      <span class="value num">
        {#if vault}
          <strong>{vault.name}</strong> · {vault.articleCount.toLocaleString()} notes
        {:else if loaded}
          None yet — set one up with the wiki CLI
        {:else}
          …
        {/if}
      </span>
    </div>

    {#if vault && !vault.accessible}
      <div class="row">
        <span class="grow">Grant file access <span class="muted">(iCloud Drive)</span></span>
        <Button size="s" variant="quiet" onclick={() => void loadVault()}>Re-check</Button>
        <Button size="s" onclick={() => window.vault.openFullDiskAccess()}>Open Settings</Button>
      </div>
    {/if}

    {#if listener}
      <div class="row">
        <span class="grow">
          Background capture
          <span class="sub">Records screen, mic and system audio — pause any time from the menu bar.</span>
        </span>
        <Switch bind:checked={capture} label="Background capture" onchange={(v) => void setCapture(v)} />
      </div>
    {/if}

    <div class="row">
      <span class="grow">Start at login</span>
      <Switch bind:checked={loginItem} label="Start at login" onchange={(v) => void setLogin(v)} />
    </div>
  </section>

  <Button variant="primary" onclick={() => window.app.onboardingDone()}>Get started</Button>
</main>

<style>
  .onboarding {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
    padding: var(--space-6) var(--space-5) var(--space-5);
  }
  .hero {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--space-2);
    text-align: center;
  }
  .logo {
    display: inline-flex;
    color: var(--accent);
  }
  h1 {
    font-size: var(--fs-xl);
    font-weight: 600;
  }
  .lede {
    color: var(--text-muted);
    max-width: 36ch;
    text-wrap: balance;
  }
  .grow {
    flex: 1;
    min-width: 0;
  }
  .sub {
    display: block;
    margin-top: 2px;
    font-size: var(--fs-s);
    color: var(--text-muted);
  }
  .muted {
    color: var(--text-muted);
  }
  .value {
    color: var(--text-muted);
    text-align: right;
  }
  .value strong {
    color: var(--text);
    font-weight: 600;
  }
</style>
