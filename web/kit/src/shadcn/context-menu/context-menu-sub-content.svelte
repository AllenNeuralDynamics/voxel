<script lang="ts">
  import { ContextMenu as ContextMenuPrimitive } from 'bits-ui';
  import type { ComponentProps } from 'svelte';

  import type { WithoutChildrenOrChild } from '../../utils/cn';
  import { cn } from '../../utils/cn';
  import ContextMenuPortal from './context-menu-portal.svelte';

  // The gap clears the menu's padding, so a submenu sits beside its menu, not over it.
  let {
    ref = $bindable(null),
    portalProps,
    class: className,
    sideOffset = 8,
    ...restProps
  }: ContextMenuPrimitive.SubContentProps & {
    portalProps?: WithoutChildrenOrChild<ComponentProps<typeof ContextMenuPortal>>;
  } = $props();
</script>

<ContextMenuPortal {...portalProps}>
  <ContextMenuPrimitive.SubContent
    bind:ref
    data-slot="context-menu-sub-content"
    class={cn(
      'z-50 min-w-32 origin-(--bits-context-menu-content-transform-origin) overflow-hidden frame-floating p-1 text-fg data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-end-2 data-[side=right]:slide-in-from-start-2 data-[side=top]:slide-in-from-bottom-2 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95',
      className
    )}
    {sideOffset}
    {...restProps}
  />
</ContextMenuPortal>
