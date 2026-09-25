<script lang="ts" generics="T">
  import type { Snippet } from 'svelte';

  import { getSortableContext } from './sortable.svelte';

  interface Props {
    item: T;
    children: Snippet;
    disabled?: boolean;
    class?: string;
  }

  let { item, children, disabled = false, class: className = '' }: Props = $props();

  const list = getSortableContext<T>();
</script>

<!-- svelte-ignore a11y_no_static_element_interactions (Pointer sorting enhances editable list content.) -->
<span class={className} onpointerdown={(event) => list.begin(item, event, disabled)}>
  {@render children()}
</span>
