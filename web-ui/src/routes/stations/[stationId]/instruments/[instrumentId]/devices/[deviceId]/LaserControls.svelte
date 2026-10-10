<script lang="ts">
  import { ChevronDown, ContentSaveOutline, Loader2 } from '$lib/icons';
  import { Select } from '$lib/kit';
  import Switch from '$lib/kit/Switch.svelte';
  import {
    EnumeratedModel,
    type Instrument,
    type LaserHandle,
    type ModulationMode,
    NumericModel,
    type Prop
  } from '$lib/model';
  import { formatPropDisplay, PropInput } from '$lib/prop';
  import LinkIndicator from '$lib/prop/LinkIndicator.svelte';
  import { SpinBox } from '$lib/prop/numeric';
  import { toastError } from '$lib/utils';

  import GenericCommands from './GenericCommands.svelte';
  import GenericProperties from './GenericProperties.svelte';
  import LaserTelemetry from './LaserTelemetry.svelte';

  let { laser, instrument }: { laser: LaserHandle; instrument: Instrument } = $props();
  const customProperties = [
    'wavelength',
    'source_power_setpoint_mw',
    'source_power_mw',
    'output_level_percent',
    'output_power_mw',
    'is_source_enabled',
    'is_output_enabled',
    'modulation_mode',
    'temperature_c'
  ];
  const customCommands = ['source_enable', 'source_disable', 'output_enable', 'output_disable', 'set_modulation_mode'];
  const modeLabels: Record<ModulationMode, string> = { software: 'Software', digital: 'Digital', analog: 'Analog' };
  const mode = $derived(String(laser.modulationMode?.value ?? ''));
  const modes = $derived(
    laser.modulationMode?.model instanceof EnumeratedModel
      ? laser.modulationMode.model.options.filter(
          (value): value is ModulationMode => typeof value === 'string' && Object.hasOwn(modeLabels, value)
        )
      : []
  );
  const blocked = $derived(!laser.connected || Boolean(laser.error) || instrument.mode === 'capture');
  const sourceEnabled = $derived(laser.sourceEnabled?.value === true);
  const outputEnabled = $derived(laser.outputEnabled?.value === true);
  const additionalProperties = $derived(
    Object.keys(laser.interface?.properties ?? {}).some((name) => !customProperties.includes(name))
  );
  const additionalCommands = $derived(
    Object.keys(laser.interface?.commands ?? {}).some((name) => !customCommands.includes(name))
  );
  const saved = $derived(instrument.divergence.get(laser.id));
  let waitForStartup = $state(true);

  function readout(value: unknown, units: string): string {
    return typeof value === 'number' && Number.isFinite(value) ? formatPropDisplay(value, units) : '—';
  }
</script>

{#snippet setting(prop: Prop | undefined, label: string)}
  {#if prop}
    {@const fixed = prop.model instanceof EnumeratedModel && prop.model.options.length === 1}
    <div class="grid grid-cols-[6rem_minmax(0,1fr)] items-center gap-3" role="group" aria-label={label}>
      <span class="flex items-center gap-1.5 text-fg-muted" title={prop.info.desc ?? ''}>
        {label}
        <LinkIndicator {instrument} deviceId={laser.id} property={prop.info.name} />
        {#if saved?.autosave.has(prop.info.name)}
          <span title="Autosaved to the active profile"><ContentSaveOutline class="size-3 text-fg-faint" /></span>
        {/if}
      </span>
      {#if fixed || prop.access !== 'rw'}
        <span class="text-right font-mono text-fg" title={fixed ? 'Fixed setting' : undefined}
          >{formatPropDisplay(prop.value, prop.units)}</span
        >
      {:else if prop.model instanceof NumericModel}
        <SpinBox
          model={prop.model}
          disabled={blocked || laser.isBusy}
          suffix={prop.units}
          align="right"
          steppers={false}
          size="xs"
        />
      {:else}
        <PropInput model={prop.model} disabled={blocked || laser.isBusy} size="xs" />
      {/if}
    </div>
  {/if}
{/snippet}

<div class="space-y-4">
  <section class="rounded-lg border border-line-muted pb-3" aria-labelledby="laser-source-heading">
    <header class="flex items-center justify-between gap-3 px-3">
      <h2 id="laser-source-heading" class="my-2.5 text-base text-fg">Source</h2>
      <div class="flex items-center gap-2" title="Source permission; output is controlled separately">
        {#if laser.pendingCommands.has('source_enable') || laser.pendingCommands.has('source_disable')}
          <Loader2 class="size-3 animate-spin text-fg-muted" />
        {/if}
        <Switch
          aria-label="Enable source"
          checked={sourceEnabled}
          disabled={blocked || laser.isBusy}
          onCheckedChange={(enabled) =>
            toastError(enabled ? laser.enableSource(waitForStartup) : laser.disableSource())}
          size="xs"
        />
      </div>
    </header>
    <div class="space-y-2 px-3">
      {@render setting(laser.sourcePowerSetpoint, 'Power')}
      <div class="flex items-center justify-between gap-3 text-fg-muted" title="Power reported by the source">
        <span>Reported</span><span class="font-mono">{readout(laser.sourcePower?.value, 'mW')}</span>
      </div>
      {#if typeof laser.temperature?.value === 'number'}
        <div class="flex items-center justify-between gap-3 text-fg-muted">
          <span>Temperature</span><span class="font-mono">{readout(laser.temperature.value, '°C')}</span>
        </div>
      {/if}
    </div>
  </section>

  <section class="rounded-lg border border-line-muted pb-3" aria-labelledby="laser-output-heading">
    <header class="flex items-center justify-between gap-3 px-3">
      <h2 id="laser-output-heading" class="my-2.5 text-base text-fg">Output</h2>
      <div
        class="flex items-center gap-2"
        title={sourceEnabled
          ? 'Permit output; external signals still control emission in digital or analog mode'
          : 'Enable the source first'}
      >
        {#if laser.pendingCommands.has('output_enable') || laser.pendingCommands.has('output_disable')}
          <Loader2 class="size-3 animate-spin text-fg-muted" />
        {/if}
        <Switch
          aria-label="Enable output"
          checked={outputEnabled}
          disabled={blocked || laser.isBusy || (!outputEnabled && !sourceEnabled)}
          onCheckedChange={(enabled) =>
            toastError(enabled ? laser.enableOutput(waitForStartup) : laser.disableOutput())}
          size="xs"
        />
      </div>
    </header>
    <div class="space-y-2 px-3">
      <div
        class="grid grid-cols-[6rem_minmax(0,1fr)] items-center gap-3"
        title={outputEnabled
          ? 'Disable output to change mode'
          : 'Software: internal level. Digital: external gate. Analog: external level.'}
      >
        <span class="text-fg-muted">Mode</span>
        <Select
          aria-label="Modulation mode"
          value={mode}
          options={modes.map((value) => ({ value, label: modeLabels[value] }))}
          onchange={(value) => toastError(laser.setModulationMode(value as ModulationMode))}
          disabled={blocked || laser.isBusy || outputEnabled || modes.length < 2}
          size="xs"
        />
      </div>
      <div
        title={mode === 'analog'
          ? 'Stored for software or digital mode; the analog signal controls the current output'
          : undefined}
      >
        {@render setting(laser.outputLevel, mode === 'analog' ? 'Level (saved)' : 'Level')}
      </div>
      <div
        class="flex items-center justify-between gap-3 text-fg-muted"
        title="Measured optical output; unavailable without a reading"
      >
        <span>Measured</span><span class="font-mono">{readout(laser.outputPower?.value, 'mW')}</span>
      </div>
    </div>
  </section>

  <LaserTelemetry {laser} />

  <label
    class="flex items-center gap-2 text-sm text-fg-muted"
    title="Enable commands wait for the driver's startup check or delay, without guaranteeing optical stability"
  >
    <input type="checkbox" bind:checked={waitForStartup} disabled={blocked || laser.isBusy} class="accent-primary" />
    Wait on enable
  </label>

  {#if additionalProperties || additionalCommands}
    <details class="group rounded-lg border border-line-muted p-3">
      <summary class="flex cursor-pointer list-none items-center justify-between text-base text-fg">
        Driver controls<ChevronDown
          class="size-3.5 -rotate-90 text-fg-muted transition-transform group-open:rotate-0"
        />
      </summary>
      <div class="space-y-3 pt-3">
        {#if additionalProperties}<GenericProperties device={laser} exclude={customProperties} {instrument} />{/if}
        {#if additionalCommands}<GenericCommands device={laser} exclude={customCommands} />{/if}
      </div>
    </details>
  {/if}
</div>
