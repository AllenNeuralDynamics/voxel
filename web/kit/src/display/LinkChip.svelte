<script lang="ts">
  import type { Snippet } from 'svelte';

  interface Props {
    href: string;
    color?: string | null;
    children: Snippet;
  }

  let { href, color, children }: Props = $props();
</script>

<a
  {href}
  class="inline-flex items-center gap-1.5 rounded-sm bg-element-bg px-1.5 text-sm/5 text-fg transition-colors hover:bg-element-hover focus-visible:outline-2 focus-visible:outline-focus"
>
  {#if color}<span class="size-2 shrink-0 rounded-full" style:background-color={color}></span>{/if}
  {@render children()}
</a>
