<script lang="ts" generics="T">
  import { onDestroy, type Snippet } from 'svelte';
  import { flip } from 'svelte/animate';

  import * as ScrollArea from '$lib/kit/cn/scroll-area';

  import type { SortableLayout } from './placement';
  import { setSortableContext, SortableState } from './sortable.svelte';

  interface Props {
    items: T[];
    key: (item: T) => string;
    onReorder: (reordered: T[]) => void;
    item: Snippet<[T, number]>;
    layout?: SortableLayout;
    threshold?: number;
    /** Layout and padding of the sortable list, inside the scroll viewport. */
    class?: string;
    /** Sizing, borders, and positioning of the outer scroll container. */
    containerClass?: string;
    ariaLabel?: string;
    flipDuration?: number;
  }

  let {
    items,
    key,
    onReorder,
    item,
    layout = 'vertical',
    threshold = 4,
    class: className = '',
    containerClass = '',
    ariaLabel = 'Sortable list',
    flipDuration = 120
  }: Props = $props();

  const list = new SortableState<T>();
  let viewport = $state<HTMLDivElement | null>(null);
  setSortableContext(list);
  onDestroy(() => list.dispose());

  $effect(() => {
    if (viewport) return list.attach(viewport);
  });

  $effect(() => {
    list.key = key;
    list.onReorder = onReorder;
    list.layout = layout;
    list.threshold = threshold;
    list.sync(items);
  });
</script>

<ScrollArea.Root
  bind:viewportRef={viewport}
  class={containerClass}
  orientation={layout === 'horizontal' ? 'horizontal' : 'vertical'}
  viewportProps={{
    'aria-label': ariaLabel,
    role: 'region',
    class: 'overscroll-contain [overflow-anchor:none]'
  }}
>
  <div class={className}>
    {#each list.items as entry, index (list.key(entry))}
      <div animate:flip={{ duration: flipDuration }}>
        {@render item(entry, index)}
      </div>
    {/each}
  </div>
</ScrollArea.Root>
