<script lang="ts">
  import type { HTMLLiAttributes } from 'svelte/elements';

  import { cn, type WithElementRef } from '$lib/core/utils';
  import { ChevronRight } from '$lib/kit/icons';

  let { ref = $bindable(null), class: className, children, ...restProps }: WithElementRef<HTMLLiAttributes> = $props();
</script>

<li
  bind:this={ref}
  data-slot="breadcrumb-separator"
  role="presentation"
  aria-hidden="true"
  class={cn('shrink-0 text-fg-faint [&>svg]:size-3.5', className)}
  {...restProps}
>
  {#if children}
    {@render children?.()}
  {:else}
    <ChevronRight />
  {/if}
</li>
