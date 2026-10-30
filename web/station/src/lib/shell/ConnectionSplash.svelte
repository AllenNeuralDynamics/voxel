<script lang="ts">
  import { getVoxelStation } from '$lib/context.svelte';
  import { cn } from '$lib/core/utils';
  import { AppearanceMenu } from '$lib/kit/themes';

  import VoxelLogo from './VoxelLogo.svelte';

  const app = getVoxelStation();
  const connectionState = $derived(app.client.state);

  const borderClass = $derived(
    connectionState === 'failed' ? 'border-danger-muted bg-danger-tint' : 'border-line-muted'
  );
</script>

<div class="flex h-screen w-full items-center justify-center bg-canvas">
  <div class={cn('flex min-h-60 w-full max-w-md flex-col rounded-lg border', borderClass)}>
    <div class="flex items-center justify-between gap-2 px-6 py-4">
      <div class="flex items-center gap-2">
        <VoxelLogo class="size-6 " />
        <h1 class="text-2xl font-light tracking-wide text-fg uppercase">Voxel</h1>
      </div>
      <AppearanceMenu />
    </div>

    <hr class={cn('border-line-muted', borderClass)} />

    <div class="flex flex-1 items-center justify-between gap-4 p-8">
      <div class="flex min-w-0 flex-col gap-2">
        {#if connectionState === 'failed'}
          <p class="text-lg text-danger-fg">Connection Failed</p>
        {:else}
          <p class="text-lg text-fg-muted">Connecting&hellip;</p>
        {/if}
        <p class="truncate font-mono text-base text-fg-muted" title={app.client.wsUrl}>
          {app.client.wsUrl}
        </p>
      </div>

      {#if connectionState === 'failed'}
        <div
          class="flex size-16 shrink-0 items-center justify-center rounded-full border-3 border-danger-fg text-danger-fg"
        >
          <span class="text-4xl leading-none font-black">!</span>
        </div>
      {:else}
        <div class="size-16 shrink-0 animate-spin rounded-full border-3 border-line-muted border-t-accent"></div>
      {/if}
    </div>

    <hr class={cn('border-line-muted', borderClass)} />

    <div class="flex h-ui-lg items-center justify-end gap-2 px-4">
      {#if connectionState === 'failed'}
        <button
          class="flex-1 cursor-pointer px-2 py-1 text-center text-base hover:text-danger-fg"
          onclick={() => app.retryConnection()}
        >
          Retry
        </button>
      {/if}
    </div>
  </div>
</div>
