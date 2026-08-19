<script lang="ts">
  import type { HTMLLiAttributes } from 'svelte/elements';

  import { LucideChevronRight } from '$lib/icons';
  import { cn, type WithElementRef } from '$lib/utils';

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
    <LucideChevronRight />
  {/if}
</li>
