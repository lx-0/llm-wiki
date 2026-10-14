<script lang="ts">
  import { icon } from '../../ui/icons';
  import { panel } from './store.svelte';

  interface NavItem {
    label: string;
    glyph: string;
    open: () => void;
    /** show the pending inbox count */
    badge: boolean;
  }

  const NAV: NavItem[] = [
    { label: 'Overview', glyph: icon.overview(15), open: () => window.app.openOverview(), badge: false },
    { label: 'Notes', glyph: icon.notes(15), open: () => window.app.openBrowse(), badge: false },
    { label: 'Inbox', glyph: icon.inbox(15), open: () => window.app.openTriage(), badge: true },
  ];
</script>

<header class="header">
  <div class="brand">
    <span class="logo">{@html icon.logo(18)}</span>
    <span class="name">llm-wiki</span>
    {#if panel.vault}
      <button class="vault" title="Open in Obsidian" onclick={() => void window.vault.openInObsidian()}>
        {panel.vault.name}{@html icon.external(11)}
      </button>
    {/if}
    <button class="gear" title="Settings" aria-label="Settings" onclick={() => window.app.openSettings()}>
      {@html icon.settings(15)}
    </button>
  </div>
  <nav class="nav" aria-label="Windows">
    {#each NAV as item}
      <button class="nav-item" onclick={item.open}>
        {@html item.glyph}
        <span>{item.label}</span>
        {#if item.badge && panel.inbox > 0}
          <span class="badge num">{panel.inbox}</span>
        {/if}
      </button>
    {/each}
  </nav>
</header>

<style>
  .header {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .brand {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }
  .logo {
    display: inline-flex;
    color: var(--text);
  }
  .name {
    font-weight: 600;
    font-size: var(--fs-l);
    letter-spacing: -0.01em;
  }
  .vault {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    margin-left: auto;
    height: 22px;
    padding: 0 var(--space-2);
    border: none;
    border-radius: var(--radius-s);
    background: var(--bg-sunken);
    color: var(--text-muted);
    font-size: var(--fs-xs);
    font-weight: 600;
    transition: color var(--dur-fast) var(--ease-out);
  }
  .vault:hover {
    color: var(--accent);
  }
  .gear {
    display: inline-flex;
    width: 24px;
    height: 24px;
    align-items: center;
    justify-content: center;
    border: none;
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--text-muted);
  }
  .gear:hover {
    background: var(--bg-hover);
    color: var(--text);
  }
  .nav {
    display: flex;
    gap: var(--space-1);
  }
  .nav-item {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    height: var(--control-h-s);
    padding: 0 var(--space-2);
    border: none;
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--text-muted);
    font-size: var(--fs-s);
    font-weight: 500;
    transition: background-color var(--dur-fast) var(--ease-out);
  }
  .nav-item:hover {
    background: var(--bg-hover);
    color: var(--text);
  }
  .badge {
    min-width: 16px;
    height: 16px;
    padding: 0 5px;
    border-radius: 8px;
    background: var(--accent);
    color: var(--text-on-accent);
    font-size: 10px;
    font-weight: 600;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
</style>
