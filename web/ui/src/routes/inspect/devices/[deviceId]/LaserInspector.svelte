<script lang="ts">
  import { Switch } from '$lib/kit';
  import type { Instrument } from '$lib/model';
  import { PropInput } from '$lib/prop';

  import DeviceBrowser from './DeviceBrowser.svelte';

  const laserExclusions = {
    props: ['wavelength', 'is_enabled', 'power', 'power_setpoint', 'temperature_c'],
    cmds: ['enable', 'disable']
  };

  interface Props {
    instrument: Instrument;
    deviceId: string;
  }

  let { instrument, deviceId }: Props = $props();

  const laser = $derived(instrument.lasers.get(deviceId));

  const laserColor = $derived(laser?.color);
  const enabled = $derived(laser?.isEnabled?.value === true);
  const measured = $derived(laser?.power?.value);
  const setpoint = $derived(laser?.powerSetpoint?.value);
  const temperature = $derived(laser?.temperature?.value);

  function handleToggle() {
    laser?.toggle();
  }
</script>

{#if laser?.connected}
  <div class="max-w-xl space-y-6">
    <div class="flex items-center justify-between gap-3">
      <div class="flex items-center gap-2">
        <span class="h-2.5 w-2.5 rounded-full" style="background-color: {laserColor}"></span>
        <span class="font-medium text-fg-muted">Enabled</span>
      </div>
      <Switch checked={enabled} onCheckedChange={handleToggle} size="sm" style="--switch-accent: {laserColor}" />
    </div>

    <!-- Power Setpoint -->
    {#if laser.powerSetpoint && typeof setpoint === 'number'}
      {@const ps = laser.powerSetpoint}
      {@const info = laser.interface?.properties?.['power_setpoint']}
      <div class="grid gap-1">
        <span class="text-base font-medium text-fg-muted">{info?.label ?? 'Power'}</span>
        <PropInput model={ps} size="xs" />
      </div>
    {/if}

    <!-- Status readback -->
    {#if typeof measured === 'number' || typeof temperature === 'number'}
      <div class="rounded border border-border bg-card p-3">
        <h4 class="mb-2 text-base font-medium tracking-wide text-fg-muted uppercase">Status</h4>
        <div class="grid gap-1.5 text-lg">
          {#if typeof measured === 'number'}
            <div class="flex justify-between">
              <span class="text-fg-muted">Power</span>
              <span class="font-mono text-fg">{measured.toFixed(1)} mW</span>
            </div>
          {/if}
          {#if typeof temperature === 'number'}
            <div class="flex justify-between">
              <span class="text-fg-muted">Temperature</span>
              <span class="font-mono text-fg">{temperature.toFixed(1)} &deg;C</span>
            </div>
          {/if}
        </div>
      </div>
    {/if}

    <!-- Dynamic: remaining properties + commands -->
    <DeviceBrowser device={laser} exclusions={laserExclusions} />
  </div>
{:else}
  <div class="flex items-center justify-center py-12">
    <p class="text-xl text-fg-muted">Laser not available</p>
  </div>
{/if}
