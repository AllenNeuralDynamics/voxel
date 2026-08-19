<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { HTMLAnchorAttributes } from 'svelte/elements';

  import { cn, type WithElementRef } from '$lib/utils';

  let {
    ref = $bindable(null),
    children,
    child,
    class: className,
    size = 'md',
    isActive = false,
    ...restProps
  }: WithElementRef<HTMLAnchorAttributes> & {
    child?: Snippet<[{ props: Record<string, unknown> }]>;
    size?: 'sm' | 'md';
    isActive?: boolean;
  } = $props();

  const mergedProps = $derived({
    class: cn(
      'flex h-ui-xs w-full min-w-0 items-center gap-2 overflow-hidden rounded px-2 text-left font-normal text-fg-muted outline-hidden hover:bg-element-hover hover:text-fg focus-visible:ring-2 focus-visible:ring-focused active:bg-element-active active:text-fg data-[size=md]:text-base data-[size=sm]:text-sm data-active:bg-element-selected data-active:text-fg group-data-[collapsible=icon]:hidden disabled:pointer-events-none disabled:opacity-50 aria-disabled:pointer-events-none aria-disabled:opacity-50 [&>span:last-child]:truncate [&>svg]:size-4 [&>svg]:shrink-0 [&>svg]:text-fg-muted',
      className
    ),
    'data-slot': 'sidebar-menu-sub-button',
    'data-sidebar': 'menu-sub-button',
    'data-size': size,
    'data-active': isActive ? '' : undefined,
    ...restProps
  });
</script>

{#if child}
  {@render child({ props: mergedProps })}
{:else}
  <a bind:this={ref} {...mergedProps}>
    {@render children?.()}
  </a>
{/if}
