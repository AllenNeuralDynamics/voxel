<script lang="ts">
  import { DropdownMenu as DropdownMenuPrimitive } from 'bits-ui';
  import type { Snippet } from 'svelte';

  import { Check as CheckIcon } from '../../icons';
  import { Minus as MinusIcon } from '../../icons';
  import { cn, type WithoutChildrenOrChild } from '../../utils/cn';

  let {
    ref = $bindable(null),
    checked = $bindable(false),
    indeterminate = $bindable(false),
    class: className,
    indicator = true,
    children: childrenProp,
    ...restProps
  }: WithoutChildrenOrChild<DropdownMenuPrimitive.CheckboxItemProps> & {
    children?: Snippet<[{ checked: boolean; indeterminate: boolean }]>;
    /** Draw the check mark. Turn it off when the content draws its own mark from `checked`. */
    indicator?: boolean;
  } = $props();
</script>

<DropdownMenuPrimitive.CheckboxItem
  bind:ref
  bind:checked
  bind:indeterminate
  data-slot="dropdown-menu-checkbox-item"
  class={cn(
    "relative flex cursor-default items-center gap-2 rounded-sm py-1.5 pe-2 text-base outline-hidden select-none focus:bg-element-hover focus:text-fg data-disabled:pointer-events-none data-disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
    indicator ? 'ps-8' : 'ps-2',
    className
  )}
  {...restProps}
>
  {#snippet children({ checked, indeterminate })}
    {#if indicator}
      <span class="pointer-events-none absolute inset-s-2 flex size-3.5 items-center justify-center">
        {#if indeterminate}
          <MinusIcon class="size-4" />
        {:else}
          <CheckIcon class={cn('size-4', !checked && 'text-transparent')} />
        {/if}
      </span>
    {/if}
    {@render childrenProp?.({ checked, indeterminate })}
  {/snippet}
</DropdownMenuPrimitive.CheckboxItem>
