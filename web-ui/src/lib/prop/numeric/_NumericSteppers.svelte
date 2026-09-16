<script lang="ts">
  let {
    disabled = false,
    canIncrement = true,
    canDecrement = true,
    onincrement,
    ondecrement
  }: {
    disabled?: boolean;
    canIncrement?: boolean;
    canDecrement?: boolean;
    onincrement: () => void;
    ondecrement: () => void;
  } = $props();
</script>

<div class="flex h-full cursor-pointer flex-col">
  <button
    type="button"
    class="flex flex-1 items-center justify-center border-b border-control-line bg-transparent px-1 text-fg-faint transition-colors hover:bg-element-hover hover:text-fg disabled:cursor-not-allowed disabled:opacity-40"
    disabled={disabled || !canIncrement}
    aria-label="Increment"
    onclick={onincrement}
  >
    <svg width="8" height="5" viewBox="0 0 8 5" fill="currentColor"><path d="M4 0L8 5H0L4 0Z" /></svg>
  </button>
  <button
    type="button"
    class="flex flex-1 items-center justify-center bg-transparent px-1 text-fg-faint transition-colors hover:bg-element-hover hover:text-fg disabled:cursor-not-allowed disabled:opacity-40"
    disabled={disabled || !canDecrement}
    aria-label="Decrement"
    onclick={ondecrement}
  >
    <svg width="8" height="5" viewBox="0 0 8 5" fill="currentColor"><path d="M4 5L0 0H8L4 5Z" /></svg>
  </button>
</div>
