<script lang="ts">
  import { ContextMenu as ContextMenuPrimitive } from 'bits-ui';

  import { cn, type WithoutChild } from '$lib/utils';

  let {
    ref = $bindable(null),
    class: className,
    children: childrenProp,
    ...restProps
  }: WithoutChild<ContextMenuPrimitive.RadioItemProps> = $props();
</script>

<ContextMenuPrimitive.RadioItem
  bind:ref
  data-slot="context-menu-radio-item"
  class={cn(
    "relative flex cursor-default items-center gap-2 rounded-sm py-1.5 ps-8 pe-2 text-lg outline-hidden select-none data-disabled:pointer-events-none data-disabled:opacity-50 data-highlighted:bg-element-hover data-highlighted:text-fg [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
    className
  )}
  {...restProps}
>
  {#snippet children({ checked })}
    <span
      aria-hidden="true"
      class="pointer-events-none absolute inset-s-2 flex size-3.5 items-center justify-center rounded-full border border-current"
    >
      {#if checked}
        <span class="size-1.5 rounded-full bg-current"></span>
      {/if}
    </span>
    {@render childrenProp?.({ checked })}
  {/snippet}
</ContextMenuPrimitive.RadioItem>
