<script lang="ts">
  import type { HTMLAttributes } from 'svelte/elements';

  import { cn, type WithElementRef } from '../../utils/cn';

  let {
    ref = $bindable(null),
    class: className,
    children,
    ...restProps
  }: WithElementRef<HTMLAttributes<HTMLDivElement>> = $props();
</script>

<div bind:this={ref} data-slot="dialog-header" class={cn('flex flex-col gap-1 text-start', className)} {...restProps}>
  {@render children?.()}
</div>
