<script lang="ts">
  import type { ComponentProps } from 'svelte';

  import { Separator } from '$lib/kit/cn/separator';
  import { cn } from '$lib/utils';

  let { ref = $bindable(null), class: className, ...restProps }: ComponentProps<typeof Separator> = $props();
</script>

<Separator
  bind:ref
  data-slot="sidebar-separator"
  data-sidebar="separator"
  class={cn('mx-2 w-auto bg-border', className)}
  {...restProps}
/>
