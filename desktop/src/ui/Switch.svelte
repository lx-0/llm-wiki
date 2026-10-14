<script lang="ts">
  interface Props {
    checked: boolean;
    label: string;
    disabled?: boolean;
    onchange?: (checked: boolean) => void;
  }

  let { checked = $bindable(), label, disabled = false, onchange }: Props = $props();
</script>

<label class="switch" class:disabled>
  <input
    type="checkbox"
    role="switch"
    bind:checked
    {disabled}
    aria-label={label}
    onchange={() => onchange?.(checked)}
  />
  <span class="track" aria-hidden="true"><span class="knob"></span></span>
</label>

<style>
  .switch {
    display: inline-flex;
    align-items: center;
    flex: none;
  }
  input {
    position: absolute;
    width: 1px;
    height: 1px;
    opacity: 0;
    pointer-events: none;
  }
  .track {
    position: relative;
    width: 36px;
    height: 22px;
    border-radius: 11px;
    background: var(--line-strong);
    transition: background-color var(--dur-fast) var(--ease-out);
  }
  .knob {
    position: absolute;
    top: 2px;
    left: 2px;
    width: 18px;
    height: 18px;
    border-radius: 50%;
    background: var(--bg-elevated);
    box-shadow: 0 1px 2px oklch(0% 0 0 / 0.25);
    transition: transform var(--dur-fast) var(--ease-out);
  }
  input:checked + .track {
    background: var(--accent);
  }
  input:checked + .track .knob {
    transform: translateX(14px);
    background: var(--text-on-accent);
  }
  input:focus-visible + .track {
    box-shadow: var(--focus);
  }
  .disabled .track {
    opacity: 0.5;
  }
</style>
