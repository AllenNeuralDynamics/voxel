<script lang="ts">
  import type { Snippet } from 'svelte';

  import { cn } from '$lib/utils';

  interface Props {
    title: string;
    trailing?: Snippet;
    children: Snippet;
    class?: string;
  }

  let { title, trailing, children, class: className }: Props = $props();
  const id = $props.id();
</script>

<section class={cn('shrink-0 rounded-lg border border-line-muted pb-3', className)} aria-labelledby={`${id}-heading`}>
  <header class="flex items-center justify-between gap-3 px-3">
    <h2 id={`${id}-heading`} class="my-2.5 text-base text-fg">{title}</h2>
    {@render trailing?.()}
  </header>

  {@render children()}
</section>
