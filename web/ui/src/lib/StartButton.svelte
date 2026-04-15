<script lang="ts">
  import type { Session } from '$lib/app';
  import { buttonVariants } from '$lib/kit/Button.svelte';
  import { cn } from '$lib/utils';

  interface Props {
    session: Session;
    class?: string;
  }

  let { session, class: className }: Props = $props();

  const isPreviewing = $derived(session.preview.isPreviewing);
  const isAcquiring = $derived(session.mode === 'acquiring');
  const isRunning = $derived(isPreviewing || isAcquiring);

  function handleClick() {
    if (isAcquiring) session.acquisition.stop();
    else if (isPreviewing) session.preview.stopPreview();
    else session.preview.startPreview();
  }
</script>

<button
  class={cn(
    buttonVariants({ variant: isRunning ? 'danger' : 'success', size: 'lg' }),
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
