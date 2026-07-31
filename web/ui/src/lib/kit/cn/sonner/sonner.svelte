<script lang="ts">
  import { Toaster as Sonner, type ToasterProps as SonnerProps } from 'svelte-sonner';

  import { CircleCheck, Info, Loader2, OctagonX, TriangleAlert } from '$lib/icons';

  let { ...restProps }: SonnerProps = $props();
</script>

<Sonner
  theme="dark"
  class="toaster group"
  style="--normal-bg: var(--color-popover); --normal-text: var(--color-popover-foreground); --normal-border: var(--color-border);"
  {...restProps}
  >{#snippet loadingIcon()}
    <Loader2 class="size-4 animate-spin" />
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
