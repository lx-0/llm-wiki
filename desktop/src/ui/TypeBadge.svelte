<script lang="ts">
  // The entity-type token: a filled pill in the type's colour from tokens.css
  // (--type-<kind>). Unknown kinds fall back to the note colour so a new engine folder never
  // renders unstyled.
  const KNOWN = new Set(['person', 'project', 'concept', 'fact', 'area', 'map', 'link', 'note']);

  interface Props {
    kind: string;
  }

  let { kind }: Props = $props();
  const slug = $derived(kind.replace(/[^a-z]/gi, '').toLowerCase());
  const token = $derived(KNOWN.has(slug) ? slug : 'note');
</script>

<span class="badge" style="--c: var(--type-{token})">{kind}</span>

<style>
  .badge {
    display: inline-flex;
    align-items: center;
    height: 18px;
    padding: 0 var(--space-2);
    border-radius: 9px;
    font-size: var(--fs-xs);
    font-weight: 600;
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
    color: var(--c);
    background: color-mix(in oklch, var(--c) 18%, transparent);
    white-space: nowrap;
  }
</style>
