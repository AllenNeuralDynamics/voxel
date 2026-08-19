<script lang="ts">
  import type { ComponentProps } from 'svelte';

  import { PanelLeft } from '$lib/icons';
  import { Button } from '$lib/kit/cn/button';
  import { cn } from '$lib/utils';

  import { useSidebar } from './context.svelte';

  let {
    ref = $bindable(null),
    class: className,
    onclick,
    ...restProps
  }: ComponentProps<typeof Button> & {
    onclick?: (e: MouseEvent) => void;
  } = $props();

  const sidebar = useSidebar();
</script>

<Button
  bind:ref
  data-sidebar="trigger"
  data-slot="sidebar-trigger"
  variant="ghost"
  size="icon-sm"
  class={cn('cn-sidebar-trigger', className)}
  type="button"
  onclick={(e) => {
    onclick?.(e);
    sidebar.toggle();
  }}
  {...restProps}
>
  <PanelLeft />
  <span class="sr-only">Toggle Sidebar</span>
</Button>
