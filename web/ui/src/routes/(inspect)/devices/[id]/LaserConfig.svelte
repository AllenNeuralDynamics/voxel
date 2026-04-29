<script lang="ts">
  import { Slider, SpinBox, Switch } from '$lib/kit';
  import type { Microscope } from '$lib/microscope';
  import DeviceBrowser from '$lib/microscope/device/DeviceBrowser.svelte';
  import { cn, sanitizeString } from '$lib/utils';

  const laserExclusions = {
    props: ['wavelength', 'is_enabled', 'power', 'power_setpoint', 'temperature_c'],
    cmds: ['enable', 'disable']
  };

  interface Props {
    microscope: Microscope;
    deviceId: string;
  }

  let { microscope, deviceId }: Props = $props();

  const laser = $derived(microscope.lasers.get(deviceId));

  const wavelength = $derived(laser?.wavelength?.value);
  const laserColor = $derived(laser?.color);
  const enabled = $derived(laser?.isEnabled?.value === true);
  const measured = $derived(laser?.power?.value);
  const setpoint = $derived(laser?.powerSetpoint?.value);
  const temperature = $derived(laser?.temperature?.value);

  function handleToggle() {
    laser?.toggle();
  }
</script>

<!-- Header with enable switch -->
<div class="mb-6 flex items-center justify-between">
  <div class="flex items-center gap-2">
    <span class="h-2.5 w-2.5 rounded-full" style="background-color: {laserColor}"></span>
    <h2 class="text-base font-medium text-fg">
      {typeof wavelength === 'number' ? `${wavelength} nm Laser` : sanitizeString(deviceId)}
    </h2>
  </div>
  <div class="flex items-center gap-3">
    <span
      class={cn('h-2 w-2 rounded-full', laser?.connected ? 'bg-success' : 'bg-fg-muted/30')}
      title={laser?.connected ? 'Connected' : 'Disconnected'}
    ></span>
    {#if laser?.connected}
      <Switch checked={enabled} onCheckedChange={handleToggle} size="sm" style="--switch-accent: {laserColor}" />
    {/if}
  </div>
</div>

{#if laser?.connected}
  <div class="max-w-xl space-y-6">
    <!-- Power Setpoint -->
    {#if laser.powerSetpoint && typeof setpoint === 'number'}
      {@const ps = laser.powerSetpoint}
      {@const info = laser.interface?.properties?.['power_setpoint']}
      <div class="grid gap-1">
        <span class="text-xs font-medium text-fg-muted">{info?.label ?? 'Power'}</span>
        <div class="grid grid-cols-[8rem_1fr] items-center gap-3">
          <SpinBox
            value={setpoint}
            min={ps.min ?? 0}
            max={ps.max ?? 100}
            step={ps.step ?? 1}
            appearance="full"
            size="xs"
            onChange={(v) => ps.patch(v)}
          />
          <Slider
            target={setpoint}
            value={measured}
            min={ps.min ?? 0}
            max={ps.max ?? 100}
            step={ps.step ?? 1}
            onChange={(v) => ps.patch(v)}
          />
        </div>
      </div>
    {/if}

    <!-- Status readback -->
    {#if typeof measured === 'number' || typeof temperature === 'number'}
      <div class="rounded border border-border bg-card p-3">
        <h4 class="mb-2 text-xs font-medium tracking-wide text-fg-muted uppercase">Status</h4>
        <div class="grid gap-1.5 text-sm">
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
    <p class="text-base text-fg-muted">Laser not available</p>
  </div>
{/if}
