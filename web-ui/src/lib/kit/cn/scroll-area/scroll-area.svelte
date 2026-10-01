<script lang="ts">
  import { ScrollArea as ScrollAreaPrimitive } from 'bits-ui';

  import { cn, type WithoutChild, type WithoutChildrenOrChild } from '$lib/utils';

  import Scrollbar from './scroll-area-scrollbar.svelte';

  let {
    ref = $bindable(null),
    viewportRef = $bindable(null),
    class: className,
    viewportProps = {},
    orientation = 'vertical',
    type = 'scroll',
    scrollHideDelay = 600,
    children,
    ...restProps
  }: WithoutChild<ScrollAreaPrimitive.RootProps> & {
    orientation?: 'vertical' | 'horizontal' | 'both';
    /** The element that scrolls, for consumers such as Sortable. */
    viewportRef?: HTMLDivElement | null;
    viewportProps?: Omit<WithoutChildrenOrChild<ScrollAreaPrimitive.ViewportProps>, 'ref'>;
  } = $props();
</script>

<ScrollAreaPrimitive.Root
  bind:ref
  data-slot="scroll-area"
  {type}
  {scrollHideDelay}
  class={cn('relative flex min-h-0 min-w-0 flex-col overflow-hidden', className)}
  {...restProps}
>
  <ScrollAreaPrimitive.Viewport
    bind:ref={viewportRef}
    data-slot="scroll-area-viewport"
    tabindex={0}
    {...viewportProps}
    class={cn(
      'min-h-0 min-w-0 flex-1 rounded-[inherit] outline-none focus-visible:ring-1 focus-visible:ring-border-focused focus-visible:ring-inset',
      viewportProps.class
    )}
  >
    {@render children?.()}
  </ScrollAreaPrimitive.Viewport>
  {#if orientation === 'vertical' || orientation === 'both'}
    <Scrollbar orientation="vertical" />
  {/if}
  {#if orientation === 'horizontal' || orientation === 'both'}
    <Scrollbar orientation="horizontal" />
  {/if}
  <ScrollAreaPrimitive.Corner />
</ScrollAreaPrimitive.Root>
