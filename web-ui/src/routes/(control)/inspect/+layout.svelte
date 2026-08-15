<script lang="ts">
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { getVoxelApp } from '$lib/model';
  import { cn, displayName } from '$lib/utils';

  const app = getVoxelApp();

  let { children } = $props();

  const instrument = $derived(app.instrument);

  const currentPath = $derived(page.url.pathname);
  const activeDeviceId = $derived(page.params.deviceId);
  const pageTitle = $derived(activeDeviceId ? displayName(activeDeviceId) : 'Stage');

  const cameraIds = $derived(instrument ? [...instrument.cameras.keys()] : []);
  const laserIds = $derived(instrument ? [...instrument.lasers.keys()] : []);
  const signalGeneratorIds = $derived(instrument ? [...instrument.signalGenerators.keys()] : []);
  const stageIds = $derived(instrument ? [instrument.hal.stage.x, instrument.hal.stage.y, instrument.hal.stage.z] : []);
  const groupedIds = $derived(new Set([...cameraIds, ...laserIds, ...signalGeneratorIds, ...stageIds]));
  const otherIds = $derived(instrument ? [...instrument.devices.keys()].filter((id) => !groupedIds.has(id)) : []);

  const stageActive = $derived(currentPath === '/inspect');
  const stageIssue = $derived.by<'error' | 'disconnected' | null>(() => {
    const axes = stageIds.flatMap((id) => {
      const axis = instrument?.devices.get(id);
      return axis ? [axis] : [];
    });
    if (axes.some((axis) => axis.error)) return 'error';
    if (axes.some((axis) => !axis.connected)) return 'disconnected';
    return null;
  });

  function rowClass(active: boolean, hasError: boolean): string {
    return cn(
      'flex items-center gap-2 rounded px-2 py-1.5 transition-colors',
      hasError ? 'text-danger' : active ? 'text-fg' : 'text-fg-muted hover:text-fg',
      active ? 'bg-element-selected' : 'hover:bg-element-hover'
    );
  }
</script>

{#snippet deviceRow(id: string)}
  {@const device = instrument?.devices.get(id)}
  <a href={resolve(`/inspect/devices/${id}` as '/')} class={rowClass(activeDeviceId === id, !!device?.error)}>
    <span class="min-w-0 flex-1 truncate" title={displayName(id)}>{displayName(id)}</span>
    {#if device && (device.error || !device.connected)}
      <span
        class={cn('size-1.5 shrink-0 rounded-full', device.error ? 'bg-danger' : 'bg-fg-muted')}
        title={device.error ? 'Device error' : 'Disconnected'}
      ></span>
    {/if}
  </a>
{/snippet}

{#snippet deviceGroup(label: string, ids: string[])}
  <div class="mt-4 mb-1 px-2 text-sm tracking-wide text-fg-faint uppercase">{label}</div>
  <div class="flex flex-col gap-0.5">
    {#each ids as id (id)}
      {@render deviceRow(id)}
    {/each}
  </div>
{/snippet}

<div class="flex h-full overflow-hidden">
  <aside class="w-50 shrink-0 overflow-hidden border-r border-border">
    <div class="flex h-full w-full flex-col overflow-y-auto py-3">
      {#if instrument}
        <div class="flex flex-col gap-0.5 px-2">
          <a
            href={resolve('/inspect')}
            class={cn(
              'flex items-center gap-2 rounded px-2 py-1.5 transition-colors',
              stageActive ? 'bg-element-selected text-fg' : 'text-fg-muted hover:bg-element-hover hover:text-fg'
            )}
          >
            <span class="min-w-0 flex-1 truncate">Stage</span>
            {#if stageIssue}
              <span
                class={cn('size-1.5 shrink-0 rounded-full', stageIssue === 'error' ? 'bg-danger' : 'bg-fg-muted')}
                title={stageIssue === 'error' ? 'Stage axis error' : 'Stage axis disconnected'}
              ></span>
            {/if}
          </a>
          {#if cameraIds.length > 0}
            {@render deviceGroup('Cameras', cameraIds)}
          {/if}
          {#if laserIds.length > 0}
            {@render deviceGroup('Lasers', laserIds)}
          {/if}
          {#if signalGeneratorIds.length > 0}
            {@render deviceGroup('Signal Generators', signalGeneratorIds)}
          {/if}
          {#if otherIds.length > 0}
            {@render deviceGroup('Other Devices', otherIds)}
          {/if}
        </div>
      {:else}
        <p class="px-4 py-1 text-fg-faint">No active instrument</p>
      {/if}
    </div>
  </aside>

  <div class="flex min-w-0 flex-1 flex-col">
    <header class="shrink-0">
      <div class="flex min-h-12 items-center px-4 py-2">
        <h1 class="truncate text-2xl font-medium text-fg">{pageTitle}</h1>
      </div>
    </header>
    <div class="min-h-0 flex-1 overflow-y-auto">
      {@render children()}
    </div>
  </div>
</div>
