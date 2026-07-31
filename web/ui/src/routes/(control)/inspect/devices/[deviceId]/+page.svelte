<script lang="ts">
  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { getVoxelApp } from '$lib/model';

  import CameraInspector from './CameraInspector.svelte';
  import DeviceBrowser from './DeviceBrowser.svelte';
  import LaserInspector from './LaserInspector.svelte';
  import SignalGeneratorInspector from './SignalGeneratorInspector.svelte';

  const app = getVoxelApp();
  const instrument = $derived(app.instrument);
  const deviceId = $derived(page.params.deviceId!);
  const stageAxis = $derived.by<'x' | 'y' | 'z' | null>(() => {
    if (!instrument) return null;
    if (instrument.hal.stage.x === deviceId) return 'x';
    if (instrument.hal.stage.y === deviceId) return 'y';
    if (instrument.hal.stage.z === deviceId) return 'z';
    return null;
  });

  // Stage axes have a consolidated inspector; redirect legacy device URLs to it.
  $effect(() => {
    if (stageAxis) {
      goto(resolve(`/inspect?axis=${stageAxis}` as '/'), { replaceState: true, keepFocus: true, noScroll: true });
    } else if (instrument && !instrument.devices.has(deviceId)) {
      goto(resolve('/inspect'), { keepFocus: true, noScroll: true });
    }
  });
</script>

{#if instrument && !stageAxis && instrument.devices.has(deviceId)}
  {@const device = instrument.devices.get(deviceId)}
  <section class="px-4">
    {#if instrument.cameras.has(deviceId)}
      <CameraInspector {instrument} {deviceId} />
    {:else if instrument.lasers.has(deviceId)}
      <LaserInspector {instrument} {deviceId} />
    {:else if instrument.signalGenerators.has(deviceId)}
      <SignalGeneratorInspector {instrument} {deviceId} />
    {:else}
      <!-- Generic device config -->
      <div class="flex h-full flex-col">
        {#if device?.connected}
          <div class="min-h-0 flex-1 space-y-6">
            <DeviceBrowser {device} />
          </div>
        {:else}
          <div class="flex items-center justify-center py-12">
            <p class="text-xl text-fg-muted">Device not available</p>
          </div>
        {/if}
      </div>
    {/if}
  </section>
{/if}
