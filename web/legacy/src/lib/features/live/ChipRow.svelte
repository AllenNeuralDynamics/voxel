<script lang="ts">
  import type { Snippet } from 'svelte';

  import { cn } from '@voxel/kit/cn';
  import { RotateCcw } from '@voxel/kit/icons';

  let {
    label,
    restorable,
    disabled = false,
    restoreTitle,
    restoreLabel,
    onRestore,
    children
  }: {
    label: string;
    restorable: boolean;
    disabled?: boolean;
    restoreTitle: string;
    restoreLabel: string;
    onRestore: () => void;
    children: Snippet;
  } = $props();
</script>

<!-- The row takes the height of an xs control, the same as the setting rows. -->
<div class="flex h-ui-sm min-w-0 items-stretch gap-2" role="group" aria-label={label}>
  <span class="flex w-20 shrink-0 items-center pr-1 text-sm text-fg-muted">{label}</span>
  <div class="flex min-w-0 flex-1 items-center gap-1">
    {@render children()}
    <!-- Shows only while a chip is off; the slot stays so nothing moves. -->
    <button
      type="button"
      class={cn(
        'flex size-6 shrink-0 items-center justify-center rounded-sm text-fg transition-colors focus-visible:outline-2 focus-visible:outline-focus enabled:hover:bg-element-hover disabled:cursor-not-allowed disabled:opacity-40',
        !restorable && 'invisible'
      )}
      {disabled}
      title={restoreTitle}
      aria-label={restoreLabel}
      onclick={onRestore}
    >
      <RotateCcw class="size-3.5" />
    </button>
  </div>
</div>
