<script lang="ts">
  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { getSessionContext } from '$lib/context';
  import DeviceBrowser from '$lib/microscope/device/DeviceBrowser.svelte';
  import { cn, sanitizeString } from '$lib/utils';

  import AnalogOutConfig from './AnalogOutConfig.svelte';
  import CameraConfig from './CameraConfig.svelte';
  import LaserConfig from './LaserConfig.svelte';

  const session = getSessionContext();
  const scope = $derived(session.scope);
  const deviceId = $derived(page.params.id!);
  const device = $derived(scope.get(deviceId));

  // Redirect if this route points at a device that no longer exists
  $effect(() => {
    if (!scope.devices.has(deviceId)) {
      goto(resolve('/' as const), { keepFocus: true, noScroll: true });
    }
  });
</script>

{#if scope.devices.has(deviceId)}
  <section class="px-4">
    {#if scope.cameras.has(deviceId)}
      <CameraConfig microscope={scope} {deviceId} />
    {:else if scope.lasers.has(deviceId)}
      <LaserConfig microscope={scope} {deviceId} />
    {:else if scope.analogOuts.has(deviceId)}
      <AnalogOutConfig microscope={scope} {deviceId} />
    {:else}
      <!-- Generic device config -->
      <div class="flex h-full flex-col gap-6">
        <div class="flex items-center justify-between">
          <h2 class="text-base font-medium text-fg">{sanitizeString(deviceId)}</h2>
          <span
            class={cn('h-2 w-2 rounded-full', device?.connected ? 'bg-success' : 'bg-fg-muted/30')}
            title={device?.connected ? 'Connected' : 'Disconnected'}
          ></span>
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
