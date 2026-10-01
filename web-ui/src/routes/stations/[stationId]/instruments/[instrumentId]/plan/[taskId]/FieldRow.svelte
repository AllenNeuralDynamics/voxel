<script lang="ts">
  import type { Snippet } from 'svelte';

  import { cn } from '$lib/utils';

  interface Props {
    label: string;
    trailing?: Snippet;
    children: Snippet;
    fieldsClass?: string;
  }

  let { label, trailing, children, fieldsClass }: Props = $props();
</script>

<div class="mx-3 grid min-w-0 grid-cols-[6rem_minmax(0,1fr)] items-start gap-x-3" role="group" aria-label={label}>
  <div class="flex h-ui-xs items-center gap-1.5 text-base text-fg-muted">
    <span>{label}</span>
    {@render trailing?.()}
  </div>

  <div class={cn('flex min-w-0 flex-wrap gap-2 *:min-w-0 *:grow *:basis-42', fieldsClass)}>
    {@render children()}
  </div>
</div>
