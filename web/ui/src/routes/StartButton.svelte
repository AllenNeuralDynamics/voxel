<script lang="ts">
  import type { Session } from '$lib/session.svelte';
  import { buttonVariants } from '$lib/kit/Button.svelte';
  import { cn } from '$lib/utils';

  interface Props {
    session: Session;
    class?: string;
  }

  let { session, class: className }: Props = $props();

  const isPreviewing = $derived(session.mode === 'previewing');
  const isAcquiring = $derived(session.mode === 'acquiring');

  function handleClick() {
    if (isAcquiring) session.acquisition.stop();
    else if (isPreviewing) session.preview.stopPreview();
    else session.preview.startPreview();
  }
</script>

<button
  class={cn(
    buttonVariants({ variant: isPreviewing || isAcquiring ? 'danger' : 'success', size: 'lg' }),
    'min-w-44 rounded-md',
    className
  )}
  onclick={handleClick}
>
  {#if isAcquiring}
    Stop Acquisition
  {:else if isPreviewing}
    Stop Preview
  {:else}
    Start Preview
  {/if}
</button>
