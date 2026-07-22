<script lang="ts">
  import type { Snippet } from 'svelte';

  import { cn } from '$lib/utils';

  interface Props {
    for?: string;
    title?: string;
    class?: string;
    children: Snippet;
  }

  let { for: forId, title, class: className, children }: Props = $props();
</script>

{#if forId}
  <label for={forId} {title} class={cn('text-base text-fg-muted', className)}>{@render children()}</label>
{:else}
  <span {title} class={cn('text-base text-fg-muted', className)}>{@render children()}</span>
{/if}
