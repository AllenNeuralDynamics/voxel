<script lang="ts">
  import { DropdownMenu as DropdownMenuPrimitive } from 'bits-ui';

  import { Circle as CircleIcon } from '../../icons';
  import { cn, type WithoutChild } from '../../utils/cn';

  let {
    ref = $bindable(null),
    class: className,
    indicator = true,
    children: childrenProp,
    ...restProps
  }: WithoutChild<DropdownMenuPrimitive.RadioItemProps> & {
    /** Draw the dot for the checked item. Turn it off when the content draws its own mark from `checked`. */
    indicator?: boolean;
  } = $props();
</script>

<DropdownMenuPrimitive.RadioItem
  bind:ref
  data-slot="dropdown-menu-radio-item"
  class={cn(
    "relative flex cursor-default items-center gap-2 rounded-sm py-1.5 pe-2 text-base outline-hidden select-none focus:bg-element-hover focus:text-fg data-disabled:pointer-events-none data-disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
    indicator ? 'ps-8' : 'ps-2',
    className
  )}
  {...restProps}
>
  {#snippet children({ checked })}
    {#if indicator}
      <span class="pointer-events-none absolute inset-s-2 flex size-3.5 items-center justify-center">
        {#if checked}
          <CircleIcon class="size-2 fill-current" />
        {/if}
      </span>
    {/if}
    {@render childrenProp?.({ checked })}
  {/snippet}
</DropdownMenuPrimitive.RadioItem>
