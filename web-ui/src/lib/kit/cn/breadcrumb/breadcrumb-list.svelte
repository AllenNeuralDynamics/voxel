<script lang="ts">
  import type { HTMLOlAttributes } from 'svelte/elements';

  import { cn, type WithElementRef } from '$lib/utils';

  let { ref = $bindable(null), class: className, children, ...restProps }: WithElementRef<HTMLOlAttributes> = $props();
</script>

<ol
  bind:this={ref}
  data-slot="breadcrumb-list"
  class={cn('flex min-w-0 flex-nowrap items-center gap-1.5 text-sm text-fg-muted', className)}
  {...restProps}
>
  {@render children?.()}
</ol>
