<script lang="ts" generics="T">
  import type { Snippet } from 'svelte';

  import { getSortableContext } from './sortable.svelte';

  interface Props {
    item: T;
    children: Snippet;
    class?: string;
  }

  let { item, children, class: className = '' }: Props = $props();

  const list = getSortableContext<T>();
  let node = $state<HTMLElement>();

  $effect(() => {
    if (node) return list.register(item, node);
  });
</script>

<div bind:this={node} class={className}>
  {@render children()}
</div>
