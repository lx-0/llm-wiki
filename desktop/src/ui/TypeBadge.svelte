<script lang="ts">
  // The entity-type token: a filled pill in the type's colour from tokens.css.
  import { typeToken } from './types';

  interface Props {
    kind: string;
  }

  let { kind }: Props = $props();
</script>

<span class="badge" style="--c: var({typeToken(kind)})">{kind}</span>

<style>
  .badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 66px; /* one column width for every kind, so titles beside badges line up */
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
