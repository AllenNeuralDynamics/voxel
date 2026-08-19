<script lang="ts">
  import type { HTMLLiAttributes } from 'svelte/elements';

  import { cn, type WithElementRef } from '$lib/utils';

  let { ref = $bindable(null), class: className, children, ...restProps }: WithElementRef<HTMLLiAttributes> = $props();
</script>

<li
  bind:this={ref}
  data-slot="breadcrumb-item"
  class={cn('inline-flex min-w-0 items-center gap-1', className)}
  {...restProps}
>
  {@render children?.()}
</li>
