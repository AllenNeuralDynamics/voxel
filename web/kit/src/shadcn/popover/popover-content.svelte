<script lang="ts">
  import { Popover as PopoverPrimitive } from 'bits-ui';
  import type { ComponentProps } from 'svelte';

  import { cn, type WithoutChildrenOrChild } from '../../utils/cn';
  import PopoverPortal from './popover-portal.svelte';

  let {
    ref = $bindable(null),
    class: className,
    align = 'center',
    sideOffset = 4,
    portalProps,
    ...restProps
  }: PopoverPrimitive.ContentProps & {
    portalProps?: WithoutChildrenOrChild<ComponentProps<typeof PopoverPortal>>;
  } = $props();
</script>

<PopoverPortal {...portalProps}>
  <PopoverPrimitive.Content
    bind:ref
    data-slot="popover-content"
    {align}
    {sideOffset}
    class={cn(
      'z-50 w-72 origin-(--bits-popover-content-transform-origin) frame-floating text-fg outline-none data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-end-2 data-[side=right]:slide-in-from-start-2 data-[side=top]:slide-in-from-bottom-2 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95',
      className
    )}
    {...restProps}
  />
</PopoverPortal>
