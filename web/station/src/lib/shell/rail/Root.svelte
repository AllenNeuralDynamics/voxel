<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { HTMLAttributes } from 'svelte/elements';

  import { cn } from '@voxel/kit/cn';

  interface Props extends HTMLAttributes<HTMLElement> {
    children: Snippet;
  }

  let { class: className, children, ...rest }: Props = $props();
</script>

<nav
  class={cn('flex w-rail shrink-0 flex-col overflow-y-auto border-r border-line-muted bg-shell py-1.5', className)}
  {...rest}
>
  {@render children()}
</nav>
