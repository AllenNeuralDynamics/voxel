<script lang="ts">
  import type { HTMLAttributes } from 'svelte/elements';

  import { cn, type WithElementRef } from '$lib/utils';

  let {
    ref = $bindable(null),
    class: className,
    children,
    ...restProps
  }: WithElementRef<HTMLAttributes<HTMLElement>> = $props();
</script>

<div
  bind:this={ref}
  data-slot="sidebar-menu-badge"
  data-sidebar="menu-badge"
  class={cn(
    'pointer-events-none absolute right-1 flex h-5 min-w-5 items-center justify-center rounded bg-element-bg px-1 text-base font-medium text-fg-muted tabular-nums select-none group-data-[collapsible=icon]:hidden peer-hover/menu-button:text-fg peer-data-active/menu-button:text-fg peer-data-[size=default]/menu-button:top-1.5 peer-data-[size=lg]/menu-button:top-2.5 peer-data-[size=sm]/menu-button:top-1',
    className
  )}
  {...restProps}
>
  {@render children?.()}
</div>
