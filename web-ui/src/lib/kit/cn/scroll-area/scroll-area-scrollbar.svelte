<script lang="ts">
  import { ScrollArea as ScrollAreaPrimitive } from 'bits-ui';

  import { cn, type WithoutChildrenOrChild } from '$lib/utils';

  let {
    ref = $bindable(null),
    class: className,
    orientation = 'vertical',
    ...restProps
  }: WithoutChildrenOrChild<ScrollAreaPrimitive.ScrollbarProps> = $props();
</script>

<ScrollAreaPrimitive.Scrollbar
  bind:ref
  data-slot="scroll-area-scrollbar"
  {orientation}
  class={cn(
    'group/scrollbar z-10 flex touch-none duration-150 select-none [--scrollbar-inset:2px] data-[state=hidden]:animate-out data-[state=hidden]:fade-out-0 data-[state=visible]:animate-in data-[state=visible]:fade-in-0 motion-reduce:animate-none',
    orientation === 'vertical' ? 'w-3 py-1' : 'h-3 flex-col px-1',
    className
  )}
  {...restProps}
>
  <!-- The thumb keeps the full 12px hit target; its 4px strip uses the same outer inset on either axis. -->
  <ScrollAreaPrimitive.Thumb
    data-slot="scroll-area-thumb"
    class={cn(
      "relative flex-1 before:absolute before:rounded-full before:bg-(--scrollbar-thumb) before:transition-colors before:content-[''] group-hover/scrollbar:before:bg-(--scrollbar-thumb-hover) active:before:bg-(--scrollbar-thumb-hover) motion-reduce:before:transition-none",
      orientation === 'vertical'
        ? 'before:inset-y-0 before:inset-e-(--scrollbar-inset) before:w-1'
        : 'before:inset-x-0 before:bottom-(--scrollbar-inset) before:h-1'
    )}
  />
</ScrollAreaPrimitive.Scrollbar>
