<script lang="ts">
  import type { HTMLAttributes } from 'svelte/elements';

  import { Ellipsis } from '../../icons';
  import { cn, type WithElementRef, type WithoutChildren } from '../../utils/cn';

  let {
    ref = $bindable(null),
    class: className,
    ...restProps
  }: WithoutChildren<WithElementRef<HTMLAttributes<HTMLSpanElement>>> = $props();
</script>

<span
  bind:this={ref}
  data-slot="breadcrumb-ellipsis"
  role="presentation"
  aria-hidden="true"
  class={cn('flex size-5 items-center justify-center [&>svg]:size-4', className)}
  {...restProps}
>
  <Ellipsis />
  <span class="sr-only">More</span>
</span>
