<script lang="ts">
  import type { Instrument } from '$lib/model';

  import DeviceBrowser from './DeviceBrowser.svelte';

  interface Props {
    instrument: Instrument;
    deviceId: string;
  }

  let { instrument, deviceId }: Props = $props();

  const generator = $derived(instrument.signalGenerators.get(deviceId));

  // Ports live on the signal generator's init (HAL config), not on the instrument top level
  const initCfg = $derived((instrument.hal.devices[deviceId]?.init ?? {}) as Record<string, unknown>);
  const ports = $derived(Object.entries((initCfg.ports ?? {}) as Record<string, string>));

  const loaded = $derived(generator?.loaded);
  const engineState = $derived(generator?.state);
</script>

<div class="max-w-xl space-y-6">
  <!-- Engine state -->
  {#if engineState}
    <div class="rounded border border-border bg-card p-3">
      <h4 class="mb-2 text-base font-medium tracking-wide text-fg-muted/70 uppercase">Engine State</h4>
      <p class="font-mono text-fg">{engineState}</p>
    </div>
  {/if}

  <!-- Output ports -->
  {#if ports.length > 0}
    <div class="rounded border border-border bg-card p-3">
      <h4 class="mb-2 text-base font-medium tracking-wide text-fg-muted/70 uppercase">Output Ports</h4>
      <div class="grid gap-1.5">
        {#each ports as [name, pin] (name)}
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
      <h4 class="mb-2 text-base font-medium tracking-wide text-fg-muted/70 uppercase">Loaded Signals</h4>
      <div class="grid gap-1.5">
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
          <span class="text-fg-muted">Waveforms</span>
          <span class="font-mono text-fg">{Object.keys(loaded.waveforms).length}</span>
        </div>
      </div>
    </div>
  {/if}

  {#if generator?.connected}
    <DeviceBrowser device={generator} />
  {:else}
    <div class="flex items-center justify-center py-12">
      <p class="text-xl text-fg-muted">Signal generator not available</p>
    </div>
  {/if}
</div>
