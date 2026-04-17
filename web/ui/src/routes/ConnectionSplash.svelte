<script lang="ts">
  import type { App } from '$lib/app';
  import { Cog } from '$lib/icons';
  import VoxelLogo from '$lib/VoxelLogo.svelte';
  import { themes } from '$lib/themes';
  import { cn } from '$lib/utils';

  const { app }: { app: App } = $props();
  const connectionState = $derived(app.client.connectionState);

  const borderClass = $derived(connectionState === 'failed' ? 'border-danger/30 bg-danger/5' : 'border-border');
</script>

<div class="flex h-screen w-full items-center justify-center bg-canvas">
  <!-- Card -->
  <div class={cn('flex min-h-60 w-full max-w-md flex-col rounded-lg border', borderClass)}>
    <!-- Header: brand + settings -->
    <div class="flex items-center justify-between gap-2 px-6 py-4">
      <div class="flex items-center gap-2">
        <VoxelLogo class="h-6 w-6" />
        <h1 class="text-lg font-light tracking-wide text-fg uppercase">Voxel</h1>
      </div>
      <button
        title="Appearance"
        onclick={() => (themes.pickerOpen = true)}
        class="flex items-center rounded p-1 text-fg-muted transition-colors hover:text-fg"
      >
        <Cog width="16" height="16" />
      </button>
    </div>

    <hr class={cn('border-border', borderClass)} />

    <!-- Body: text column + large glyph, URL -->
    <div class="flex flex-1 items-center justify-between gap-4 p-8">
      <div class="flex min-w-0 flex-col gap-2">
        {#if connectionState === 'failed'}
          <p class="text-sm text-danger">Connection Failed</p>
        {:else}
          <p class="text-sm text-fg-muted">Connecting&hellip;</p>
        {/if}
        <p class="truncate font-mono text-xs text-fg-muted/70" title={app.client.wsUrl}>
          {app.client.wsUrl}
        </p>
      </div>

      {#if connectionState === 'failed'}
        <div
          class="flex size-16 shrink-0 items-center justify-center rounded-full border-3 border-danger/70 text-danger/70"
        >
          <span class="text-3xl leading-none font-black">!</span>
        </div>
      {:else}
        <div class="size-16 shrink-0 animate-spin rounded-full border-3 border-border border-t-primary"></div>
      {/if}
    </div>

    <hr class={cn('border-border', borderClass)} />

    <!-- Footer: retry -->
    <div class="flex h-ui-md items-center justify-end gap-2 px-4">
      {#if connectionState === 'failed'}
        <button
          class="flex-1 cursor-pointer px-2 py-1 text-center text-xs hover:text-danger/80"
          onclick={() => app.retryConnection()}
        >
          Retry
        </button>
      {/if}
    </div>
  </div>
</div>
