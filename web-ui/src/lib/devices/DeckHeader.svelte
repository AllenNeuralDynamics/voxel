<script lang="ts">
  import type { Snippet } from 'svelte';

  interface Props {
    title: string;
    count: number;
    actions?: Snippet;
  }

  let { title, count, actions }: Props = $props();
</script>

<div class="flex h-ui-sm shrink-0 items-center gap-2 px-3">
  <h2 class="min-w-0 flex-1 truncate text-base font-normal text-fg-muted">{title}</h2>
  {#if actions}
    <div class="flex shrink-0 items-center gap-1">
      {@render actions()}
    </div>
  {/if}
  <span class="shrink-0 font-mono text-[10px] text-fg-faint tabular-nums">{count}</span>
</div>
