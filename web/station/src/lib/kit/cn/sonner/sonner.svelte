<script lang="ts">
  import { Toaster as Sonner, type ToasterProps as SonnerProps } from 'svelte-sonner';

  import { CircleCheck, Info, Loader, OctagonX, TriangleAlert } from '$lib/kit/icons';
  import { themes } from '$lib/kit/themes/manager.svelte';

  let { ...restProps }: SonnerProps = $props();
</script>

<Sonner
  theme={themes.resolvedMode}
  class="toaster group"
  style="--normal-bg: var(--color-floating); --normal-text: var(--color-fg); --normal-border: var(--color-line-muted);"
  {...restProps}
  >{#snippet loadingIcon()}
    <Loader class="size-4 animate-spin" />
  {/snippet}
  {#snippet successIcon()}
    <CircleCheck class="size-4" />
  {/snippet}
  {#snippet errorIcon()}
    <OctagonX class="size-4" />
  {/snippet}
  {#snippet infoIcon()}
    <Info class="size-4" />
  {/snippet}
  {#snippet warningIcon()}
    <TriangleAlert class="size-4" />
  {/snippet}
</Sonner>
