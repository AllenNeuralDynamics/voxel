<script lang="ts" generics="T">
  import { onDestroy, type Snippet } from 'svelte';
  import { flip } from 'svelte/animate';

  import * as ScrollArea from '../../shadcn/scroll-area';
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
    /**
     * Scrolls in its own box, which keeps the wheel when it reaches an end. Off, the list is a plain box inside a
     * scrolling page: the wheel reaches the page, and a drag does not scroll by itself near the edges.
     */
    scroll?: boolean;
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
    scroll = true,
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

{#snippet entries()}
  <div class={className}>
    {#each list.items as entry, index (list.key(entry))}
      <div animate:flip={{ duration: flipDuration }}>
        {@render item(entry, index)}
      </div>
    {/each}
  </div>
{/snippet}

{#if scroll}
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
    {@render entries()}
  </ScrollArea.Root>
{:else}
  <div bind:this={viewport} class={containerClass} aria-label={ariaLabel} role="region">
    {@render entries()}
  </div>
{/if}
