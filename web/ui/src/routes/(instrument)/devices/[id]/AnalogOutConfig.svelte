<script lang="ts">
  import type { Session } from '$lib/app';
  import type { AOSignals } from '$lib/app';
  import { cn, sanitizeString } from '$lib/utils';
  import DeviceBrowser from '$lib/device/DeviceBrowser.svelte';

  interface Props {
    session: Session;
    deviceId: string;
  }

  let { session, deviceId }: Props = $props();

  let devicesManager = $derived(session.devices);
  let device = $derived(devicesManager.getDevice(deviceId));

  // Ports / triggers live on the AO device's init (rig config), not on the microscope top level
  const initCfg = $derived((session.rig_cfg.rig.devices?.[deviceId]?.init ?? {}) as Record<string, unknown>);
  const ports = $derived(Object.entries((initCfg.ports ?? {}) as Record<string, string>));
  const triggers = $derived(Object.entries((initCfg.triggers ?? {}) as Record<string, string>));

  // Currently loaded AOSignals (streamed by the AO device's controller). ``null`` until first load.
  const loaded = $derived(devicesManager.getPropertyValue(deviceId, 'loaded') as AOSignals | null | undefined);
  const engineState = $derived(devicesManager.getPropertyValue(deviceId, 'state') as string | undefined);
</script>

<!-- Header -->
<div class="mb-6 flex items-center justify-between">
  <h2 class="text-base font-medium text-fg">{sanitizeString(deviceId)}</h2>
  <span
    class={cn('h-2 w-2 rounded-full', device?.connected ? 'bg-success' : 'bg-fg-muted/30')}
    title={device?.connected ? 'Connected' : 'Disconnected'}
  ></span>
</div>

<div class="max-w-xl space-y-6">
  <!-- Engine state -->
  {#if engineState}
    <div class="rounded border border-border bg-card p-3">
      <h4 class="mb-2 text-xs font-medium tracking-wide text-fg-muted uppercase">Engine State</h4>
      <p class="font-mono text-sm text-fg">{engineState}</p>
    </div>
  {/if}

  <!-- Output ports -->
  {#if ports.length > 0}
    <div class="rounded border border-border bg-card p-3">
      <h4 class="mb-2 text-xs font-medium tracking-wide text-fg-muted uppercase">Output Ports</h4>
      <div class="grid gap-1.5 text-sm">
        {#each ports as [name, pin] (name)}
          <div class="flex items-center justify-between">
            <span class="text-fg">{name}</span>
            <span class="font-mono text-fg-muted">{pin}</span>
          </div>
        {/each}
      </div>
    </div>
  {/if}

  <!-- Trigger inputs -->
  {#if triggers.length > 0}
    <div class="rounded border border-border bg-card p-3">
      <h4 class="mb-2 text-xs font-medium tracking-wide text-fg-muted uppercase">Trigger Inputs</h4>
      <div class="grid gap-1.5 text-sm">
        {#each triggers as [name, pin] (name)}
          <div class="flex items-center justify-between">
            <span class="text-fg">{name}</span>
            <span class="font-mono text-fg-muted">{pin}</span>
          </div>
        {/each}
      </div>
    </div>
  {/if}

  <!-- Loaded signals summary -->
  {#if loaded}
    <div class="rounded border border-border bg-card p-3">
      <h4 class="mb-2 text-xs font-medium tracking-wide text-fg-muted uppercase">Loaded Signals</h4>
      <div class="grid gap-1.5 text-sm">
        <div class="flex items-center justify-between">
          <span class="text-fg-muted">Sample rate</span>
          <span class="font-mono text-fg">{loaded.sample_rate.toLocaleString()} Hz</span>
        </div>
        <div class="flex items-center justify-between">
          <span class="text-fg-muted">Duration</span>
          <span class="font-mono text-fg">{loaded.duration} s</span>
        </div>
        <div class="flex items-center justify-between">
          <span class="text-fg-muted">Rest time</span>
          <span class="font-mono text-fg">{loaded.rest_time} s</span>
        </div>
        <div class="flex items-center justify-between">
          <span class="text-fg-muted">Clock</span>
          <span class="font-mono text-fg">
            {loaded.clock_src.type === 'internal' ? 'internal' : `external (${loaded.clock_src.source})`}
          </span>
        </div>
        <div class="flex items-center justify-between">
          <span class="text-fg-muted">Waveforms</span>
          <span class="font-mono text-fg">{Object.keys(loaded.waveforms).length}</span>
        </div>
      </div>
    </div>
  {/if}

  {#if device?.connected}
    <DeviceBrowser {deviceId} {devicesManager} />
  {:else}
    <div class="flex items-center justify-center py-12">
      <p class="text-base text-fg-muted">AO device not available</p>
    </div>
  {/if}
</div>
