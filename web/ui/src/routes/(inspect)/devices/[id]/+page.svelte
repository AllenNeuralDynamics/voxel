<script lang="ts">
  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { getVoxelApp } from '$lib/model';
  import { cn, sanitizeString } from '$lib/utils';

  import AnalogOutInspector from './AnalogOutInspector.svelte';
  import CameraInspector from './CameraInspector.svelte';
  import DeviceBrowser from './DeviceBrowser.svelte';
  import LaserInspector from './LaserInspector.svelte';

  const app = getVoxelApp();
  const instrument = $derived(app.instrument);
  const deviceId = $derived(page.params.id!);

  // Redirect if this route points at a device that no longer exists
  $effect(() => {
    if (instrument && !instrument.devices.has(deviceId)) {
      goto(resolve('/' as const), { keepFocus: true, noScroll: true });
    }
  });
</script>

{#if instrument && instrument.devices.has(deviceId)}
  {@const device = instrument.devices.get(deviceId)}
  <section class="px-4">
    {#if instrument.cameras.has(deviceId)}
      <CameraInspector {instrument} {deviceId} />
    {:else if instrument.lasers.has(deviceId)}
      <LaserInspector {instrument} {deviceId} />
    {:else if instrument.analogOuts.has(deviceId)}
      <AnalogOutInspector {instrument} {deviceId} />
    {:else}
      <!-- Generic device config -->
      <div class="flex h-full flex-col gap-6">
        <div class="flex items-center justify-between">
          <h2 class="text-base font-medium text-fg">{sanitizeString(deviceId)}</h2>
          <span
            class={cn('h-2 w-2 rounded-full', device?.connected ? 'bg-success' : 'bg-fg-muted/30')}
            title={device?.connected ? 'Connected' : 'Disconnected'}
          >
          </span>
        </div>

        {#if device?.connected}
          <div class="min-h-0 flex-1 space-y-6">
            <DeviceBrowser {device} />
          </div>
        {:else}
          <div class="flex items-center justify-center py-12">
            <p class="text-base text-fg-muted">Device not available</p>
          </div>
        {/if}
      </div>
    {/if}
  </section>
{/if}
