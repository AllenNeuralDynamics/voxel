<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { HTMLAttributes } from 'svelte/elements';

  import { cn } from '@voxel/kit/cn';

  interface Props extends HTMLAttributes<HTMLUListElement> {
    children: Snippet;
  }

  let { class: className, children, ...rest }: Props = $props();
</script>

<ul class={cn('flex flex-col [&:not(:first-child)>li:first-child>a]:pt-3.5', className)} {...rest}>
  {@render children()}
</ul>
