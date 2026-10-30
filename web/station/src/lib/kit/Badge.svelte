<script lang="ts">
  import type { Snippet } from 'svelte';

  import { cn } from '$lib/core/utils';

  interface Props {
    tone?: 'neutral' | 'success' | 'warning' | 'danger';
    title?: string;
    class?: string;
    children: Snippet;
  }

  let { tone = 'neutral', title, class: className, children }: Props = $props();
</script>

<span
  {title}
  class={cn(
    'shrink-0 rounded-sm px-1.5 text-sm/5 ',
    {
      neutral: 'bg-tint text-fg-muted',
      success: 'bg-success-tint text-success-fg',
      warning: 'bg-warning-tint text-warning-fg',
      danger: 'bg-danger-tint text-danger-fg'
    }[tone],
    className
  )}>{@render children()}</span
>
