<script lang="ts">
  import type { App } from '$lib/app';
  import { Cog, AlertCircleOutline } from '$lib/icons';
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
    <!-- Header: brand + status indicator -->
    <div class="flex items-center justify-between gap-2 px-6 py-4">
      <div class="flex items-center gap-2">
        <VoxelLogo class="h-6 w-6" />
        <h1 class="text-lg font-light tracking-wide text-fg uppercase">Voxel</h1>
      </div>
      {#if connectionState === 'failed'}
        <AlertCircleOutline width="18" height="18" class="text-danger" />
      {:else}
        <div class="h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-border border-t-primary"></div>
      {/if}
    </div>

    <hr class={cn('border-border', borderClass)} />

    <!-- Body: state label + URL -->
    <div class="flex flex-1 flex-col justify-center gap-4 p-6">
      {#if connectionState === 'failed'}
        <p class="text-sm text-danger">Connection Failed</p>
      {:else}
        <p class="text-sm text-fg-muted">Connecting&hellip;</p>
      {/if}

      <p class="truncate font-mono text-xs text-fg-muted/70" title={app.client.wsUrl}>
        {app.client.wsUrl}
      </p>
    </div>

    <hr class={cn('border-border', borderClass)} />

    <!-- Footer: cog + retry -->
    <div class="flex items-center justify-between gap-2 px-4 py-2">
      <button
        title="Appearance"
        onclick={() => (themes.pickerOpen = true)}
        class="flex items-center rounded p-1 text-fg-muted transition-colors hover:text-fg"
      >
        <Cog width="16" height="16" />
      </button>
      {#if connectionState === 'failed'}
        <button
          class="w-30 cursor-pointer px-2 py-1 text-right text-xs hover:text-danger/80"
          onclick={() => app.retryConnection()}
        >
          Retry
        </button>
      {/if}
    </div>
  </div>
</div>
