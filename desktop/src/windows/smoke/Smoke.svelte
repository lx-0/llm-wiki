<script lang="ts">
  // Primitives sheet — renders the design tokens and shared components in every state so the
  // harness captures (light + dark) review the system itself. Not shipped in the app menu;
  // deleted at S05 closeout.
  import '../../styles/tokens.css';
  import Button from '../../ui/Button.svelte';
  import { icon } from '../../ui/icons';
  import Switch from '../../ui/Switch.svelte';
  import TypeBadge from '../../ui/TypeBadge.svelte';

  const KINDS = ['person', 'project', 'concept', 'fact', 'area', 'map', 'link', 'note'];
  const SWATCHES = [
    ['bg', '--bg'],
    ['elevated', '--bg-elevated'],
    ['sunken', '--bg-sunken'],
    ['line', '--line-strong'],
    ['accent', '--accent'],
    ['ok', '--ok'],
    ['warn', '--warn'],
    ['danger', '--danger'],
  ];
  const ICONS = Object.keys(icon) as (keyof typeof icon)[];

  let on = $state(true);
  let off = $state(false);
  let library = $state('…');

  $effect(() => {
    void window.vault.status().then((v) => {
      library = v ? `${v.name} · ${v.articleCount.toLocaleString()} notes` : 'no library';
    });
  });
</script>

<main class="sheet">
  <header class="head">
    <span class="logo">{@html icon.logo(22)}</span>
    <h1>Primitives</h1>
    <span class="muted num">{library}</span>
  </header>

  <section>
    <h2 class="caps">Surfaces & semantics</h2>
    <div class="swatches">
      {#each SWATCHES as [name, token]}
        <div class="swatch"><span class="chip" style="background: var({token})"></span><span>{name}</span></div>
      {/each}
    </div>
  </section>

  <section>
    <h2 class="caps">Entity types</h2>
    <div class="badges">
      {#each KINDS as kind}
        <TypeBadge {kind} />
      {/each}
    </div>
  </section>

  <section>
    <h2 class="caps">Buttons</h2>
    <div class="cluster">
      <Button variant="primary">Update knowledge</Button>
      <Button>Sort</Button>
      <Button variant="quiet">Dismiss</Button>
      <Button variant="primary" disabled>Updating…</Button>
      <Button size="s">Refresh</Button>
      <Button size="s" variant="quiet">{@html icon.copy(14)} Copy</Button>
    </div>
  </section>

  <section>
    <h2 class="caps">Switch · rows · card</h2>
    <div class="card">
      <div class="row"><span class="grow">Start at login</span><Switch bind:checked={on} label="Start at login" /></div>
      <div class="row"><span class="grow">Background capture</span><Switch bind:checked={off} label="Background capture" /></div>
      <div class="row"><span class="grow">File access</span><span class="muted">Granted</span></div>
    </div>
  </section>

  <section>
    <h2 class="caps">Type scale</h2>
    <p class="xxl num">2,024</p>
    <p class="xl">Window title</p>
    <p class="l">Section heading</p>
    <p>Body copy at the default size, cool-neutral text on the window surface.</p>
    <p class="s muted">Secondary line in muted ink</p>
    <p class="xs faint num">12m ago · 4 of 12</p>
  </section>

  <section>
    <h2 class="caps">Icons</h2>
    <div class="icons">
      {#each ICONS as name}
        <span class="icon" title={name}>{@html icon[name](18)}</span>
      {/each}
    </div>
  </section>
</main>

<style>
  .sheet {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
    padding: var(--space-5);
    max-width: 520px;
  }
  .head {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }
  .logo {
    display: inline-flex;
    color: var(--accent);
  }
  h1 {
    font-size: var(--fs-xl);
    font-weight: 600;
  }
  h2 {
    margin-bottom: var(--space-2);
  }
  section {
    display: flex;
    flex-direction: column;
  }
  .swatches,
  .badges,
  .cluster,
  .icons {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    align-items: center;
  }
  .swatch {
    display: flex;
    align-items: center;
    gap: var(--space-1);
    font-size: var(--fs-s);
    color: var(--text-muted);
  }
  .chip {
    width: 22px;
    height: 22px;
    border-radius: var(--radius-s);
    border: 1px solid var(--line);
  }
  .grow {
    flex: 1;
  }
  .muted {
    color: var(--text-muted);
  }
  .faint {
    color: var(--text-faint);
  }
  .xxl {
    font-size: var(--fs-xxl);
    font-weight: 600;
    line-height: 1.1;
  }
  .xl {
    font-size: var(--fs-xl);
    font-weight: 600;
  }
  .l {
    font-size: var(--fs-l);
    font-weight: 600;
  }
  .s {
    font-size: var(--fs-s);
  }
  .xs {
    font-size: var(--fs-xs);
  }
  .icon {
    display: inline-flex;
    padding: var(--space-1);
    color: var(--text-muted);
  }
</style>
