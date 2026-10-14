<script lang="ts">
  // The table twin of a chart: every value a chart shows, readable without colour or hover.
  // Numeric columns (by the first row) right-align in tabular figures.
  interface Props {
    caption: string;
    columns: string[];
    rows: (string | number)[][];
  }

  let { caption, columns, rows }: Props = $props();
  const numeric = $derived(columns.map((_, i) => rows.length > 0 && typeof rows[0][i] === 'number'));
</script>

<table class="data" aria-label={caption}>
  <thead>
    <tr>
      {#each columns as column, i (column)}
        <th scope="col" class:num={numeric[i]}>{column}</th>
      {/each}
    </tr>
  </thead>
  <tbody>
    {#each rows as row, r (r)}
      <tr>
        {#each row as cell, i}
          <td class:num={numeric[i]}>{typeof cell === 'number' ? cell.toLocaleString() : cell}</td>
        {/each}
      </tr>
    {/each}
  </tbody>
</table>

<style>
  .data {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--fs-s);
  }
  th {
    padding: 4px var(--space-2);
    border-bottom: 1px solid var(--line-strong);
    color: var(--text-muted);
    font-weight: 600;
    text-align: left;
  }
  td {
    padding: 3px var(--space-2);
    border-bottom: 1px solid var(--line);
  }
  th.num,
  td.num {
    text-align: right;
  }
  td.num {
    font-variant-numeric: tabular-nums;
  }
</style>
