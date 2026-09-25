<script lang="ts" generics="T">
  import { onDestroy, type Snippet } from 'svelte';
  import { flip } from 'svelte/animate';

  import type { SortableLayout } from './placement';
  import { setSortableContext, SortableState } from './sortable.svelte';

  interface Props {
    items: T[];
    key: (item: T) => string;
    onReorder: (reordered: T[]) => void;
    item: Snippet<[T, number]>;
    layout?: SortableLayout;
    threshold?: number;
    class?: string;
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
    flipDuration = 120
  }: Props = $props();

  const state = new SortableState<T>();
  setSortableContext(state);
  onDestroy(() => state.dispose());

  $effect(() => {
    state.key = key;
    state.onReorder = onReorder;
    state.layout = layout;
    state.threshold = threshold;
    state.sync(items);
  });
</script>

<div class={className}>
  {#each state.items as entry, index (state.key(entry))}
    <div animate:flip={{ duration: flipDuration }}>
      {@render item(entry, index)}
    </div>
  {/each}
</div>
