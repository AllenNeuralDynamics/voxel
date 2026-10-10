<script lang="ts">
  import { resolve } from '$app/paths';
  import { Loader2 } from '$lib/icons';
  import { Switch } from '$lib/kit';
  import {
    EnumeratedModel,
    type Instrument,
    type LaserHandle,
    type LaserSample,
    type ModulationMode,
    NumericModel,
    type Prop
  } from '$lib/model';
  import { Enumerated } from '$lib/prop';
  import LinkIndicator from '$lib/prop/LinkIndicator.svelte';
  import { Input } from '$lib/prop/numeric';
  import { cn, toastError } from '$lib/utils';

  import { deviceIdentity } from './snippets.svelte';

  let { laser, instrument }: { laser: LaserHandle; instrument: Instrument } = $props();
  const id = $props.id();
  const channel = $derived(instrument.activeChannels.find((channel) => channel.laser.id === laser.id));
  const color = $derived(laser.color ?? 'var(--color-fg-muted)');
  const enabled = $derived(laser.outputEnabled?.value === true);
  let switching = $state(false);
  let switchingOn = $state(false);
  const busy = $derived(switching || laser.isBusy);
  const unavailable = $derived(!laser.connected || Boolean(laser.error) || instrument.mode === 'capture');
  const disabled = $derived(unavailable || busy);
  let showPending = $state(false);
  $effect(() => {
    if (!busy) {
      showPending = false;
      return;
    }
    const timer = setTimeout(() => {
      showPending = true;
    }, 200);
    return () => clearTimeout(timer);
  });
  const pendingLabel = $derived.by(() => {
    if (switching) return switchingOn ? 'Enabling output' : 'Disabling output';
    const command = [...laser.pendingCommands][0];
    if (command)
      return (
        (
          {
            source_enable: 'Enabling source',
            source_disable: 'Disabling source',
            output_enable: 'Enabling output',
            output_disable: 'Disabling output',
            set_modulation_mode: 'Changing modulation mode'
          } as Record<string, string>
        )[command] ?? 'Updating laser'
      );
    if (laser.pendingProperties.has('source_power_setpoint_mw')) return 'Updating source power';
    if (laser.pendingProperties.has('output_level_percent')) return 'Updating output level';
    return 'Updating laser';
  });

  // Keep repeated edits to the same setting responsive while its writes finish.
  function settingDisabled(prop: Prop | undefined): boolean {
    return (
      unavailable ||
      switching ||
      laser.pendingCommands.size > 0 ||
      [...laser.pendingProperties.keys()].some((name) => name !== prop?.info.name)
    );
  }
  const modeLabels: Record<ModulationMode, string> = { software: 'Software', digital: 'Digital', analog: 'Analog' };
  const modes = $derived(
    laser.modulationMode?.model instanceof EnumeratedModel
      ? laser.modulationMode.model.options.filter(
          (mode): mode is ModulationMode => typeof mode === 'string' && Object.hasOwn(modeLabels, mode)
        )
      : []
  );
  const level = $derived(laser.outputLevel?.model);
  const levelOptions = $derived(
    level instanceof EnumeratedModel ? level.options.filter((value): value is number => typeof value === 'number') : []
  );
  const levelMin = $derived(level instanceof NumericModel ? (level.min ?? 0) : Math.min(...levelOptions));
  const levelMax = $derived(level instanceof NumericModel ? (level.max ?? 100) : Math.max(...levelOptions));
  const levelDisabled = $derived(
    settingDisabled(laser.outputLevel) ||
      !laser.outputLevelActive ||
      laser.outputLevel?.access !== 'rw' ||
      level?.disabled ||
      levelMin === levelMax
  );
  const sliderMin = $derived(level instanceof NumericModel ? levelMin : 0);
  const sliderMax = $derived(level instanceof NumericModel ? levelMax : levelOptions.length - 1);
  const sliderValue = $derived(
    level instanceof NumericModel ? level.value : levelOptions.indexOf(Number(level?.value))
  );
  const levelPosition = $derived(
    levelMax > levelMin
      ? Math.max(0, Math.min(100, ((Number(level?.value) - levelMin) / (levelMax - levelMin)) * 100))
      : 100
  );
  const source = $derived(laser.sourcePowerSetpoint?.model);
  const sourceOptions = $derived(
    source instanceof EnumeratedModel
      ? source.options.filter((value): value is number => typeof value === 'number')
      : []
  );
  const sourceMin = $derived(source instanceof NumericModel ? (source.min ?? 0) : 0);
  const sourceMax = $derived(source instanceof NumericModel ? (source.max ?? sourceMin) : sourceOptions.length - 1);
  const sourceValue = $derived(
    source instanceof NumericModel ? source.value : sourceOptions.indexOf(Number(source?.value))
  );
  const hasSourceSlider = $derived(
    source instanceof NumericModel ? source.max != null && Number.isFinite(source.max) : sourceOptions.length > 0
  );
  const sourceDisabled = $derived(
    settingDisabled(laser.sourcePowerSetpoint) ||
      laser.sourcePowerSetpoint?.access !== 'rw' ||
      source?.disabled ||
      sourceMax <= sourceMin
  );
  const sourcePosition = $derived(
    sourceMax > sourceMin
      ? Math.max(0, Math.min(100, ((sourceValue - sourceMin) / (sourceMax - sourceMin)) * 100))
      : 100
  );
  const sourceMaximum = $derived.by(() => {
    const model = laser.sourcePowerSetpoint?.model;
    const limit =
      model instanceof NumericModel
        ? (model.max ?? 0)
        : model instanceof EnumeratedModel
          ? Math.max(0, ...model.options.filter((v): v is number => typeof v === 'number'))
          : 0;
    return Math.max(
      1,
      limit,
      ...[laser.sourceSetpointHistory, laser.sourcePowerHistory, laser.outputPowerHistory].flatMap((series) =>
        series.flatMap(({ v }) => (v == null ? [] : [v]))
      )
    );
  });
  const W = 1000;
  const WINDOW_MS = 60_000;
  let now = $state(performance.now());
  $effect(() => {
    const timer = setInterval(() => {
      now = performance.now();
    }, 100);
    return () => clearInterval(timer);
  });

  async function toggleOutput(on: boolean): Promise<void> {
    switchingOn = on;
    switching = true;
    try {
      if (on) {
        await laser.enableSource(true);
        await laser.enableOutput(true);
      } else await laser.disableOutput();
    } finally {
      switching = false;
    }
  }

  function setLevel(value: number): void {
    if (levelDisabled) return;
    if (level instanceof NumericModel) level.patch(value, { throttled: true });
    else if (level instanceof EnumeratedModel && levelOptions[value] != null)
      (level as EnumeratedModel<number>).select(levelOptions[value]);
  }

  function setSource(value: number): void {
    if (sourceDisabled) return;
    if (source instanceof NumericModel) source.patch(value, { throttled: true });
    else if (source instanceof EnumeratedModel && sourceOptions[value] != null)
      (source as EnumeratedModel<number>).select(sourceOptions[value]);
  }

  // Clip each held-value segment to the visible minute; unavailable samples break both line and fill.
  function segments(samples: LaserSample[]): { line: string; area: string }[] {
    const start = now - WINDOW_MS;
    const result: { line: string; area: string }[] = [];
    let previous: number | null = null;
    let points: [number, number][] = [];
    const y = (value: number) => 100 - (value / sourceMaximum) * 100;
    const flush = () => {
      if (!points.length) return;
      const line = points.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
      result.push({ line, area: `${points[0][0]},100 ${line} ${points.at(-1)![0]},100` });
      points = [];
    };
    for (const sample of samples) {
      if (sample.t > now) break;
      if (sample.t < start) {
        previous = sample.v;
        continue;
      }
      const x = ((sample.t - start) / WINDOW_MS) * W;
      if (previous != null) {
        if (!points.length) points.push([0, y(previous)]);
        points.push([x, y(previous)]);
      }
      if (sample.v == null) flush();
      else points.push([x, y(sample.v)]);
      previous = sample.v;
    }
    if (previous != null) {
      if (!points.length) points.push([0, y(previous)]);
      points.push([W, y(previous)]);
    }
    flush();
    return result;
  }

  function reading(value: unknown): string {
    return typeof value === 'number' && Number.isFinite(value) ? Number(value.toPrecision(5)).toString() : '—';
  }
</script>

{#snippet setting(label: string, prop: Prop | undefined, units: string, inactive = false, joined = false)}
  <div
    class={cn(
      'flex h-[calc(var(--ui-xs)-2px)] min-w-0 items-center gap-1 bg-element-bg px-1 font-mono text-[10px] tabular-nums',
      !joined && 'focus-within:border-focused rounded-sm border border-control-line'
    )}
    title={inactive ? 'External analog modulation controls intensity' : (prop?.info.desc ?? '')}
  >
    {#if prop?.model instanceof NumericModel}
      <Input
        model={prop.model}
        numCharacters={5}
        significantDigits={5}
        align="right"
        class="min-w-0 flex-1 text-fg disabled:opacity-40"
        disabled={settingDisabled(prop) || inactive || prop.access !== 'rw' || prop.model.disabled}
        aria-label={label}
      />
    {:else if prop?.model instanceof EnumeratedModel && prop.model.options.length > 1}
      <Enumerated.Select
        model={prop.model as EnumeratedModel<number>}
        formatLabel={reading}
        disabled={settingDisabled(prop) || inactive || prop.access !== 'rw'}
        size="xs"
        class="min-w-0 flex-1 border-0 px-0 text-[10px]"
      />
    {:else}
      <span class="min-w-0 flex-1 text-right text-fg">{reading(prop?.value)}</span>
    {/if}
    <span class="shrink-0 text-fg-muted">{units}</span>
  </div>
{/snippet}

<div
  class="flex min-w-0 flex-col overflow-hidden rounded-xs border border-line bg-card"
  aria-label="Laser control card with horizontal level control"
>
  <div class="flex flex-wrap items-center gap-x-2 gap-y-2 px-2.5 pt-2 pb-1.5">
    <a
      href={resolve('/stations/[stationId]/instruments/[instrumentId]/devices/[deviceId]', {
        stationId: instrument.stationId,
        instrumentId: instrument.id,
        deviceId: laser.id
      })}
      class="flex items-center gap-2 rounded-sm hover:underline focus-visible:outline-2 focus-visible:outline-border-focused"
      title="Open laser device"
    >
      {@render deviceIdentity(laser.wavelength?.value ? `${laser.wavelength.value} nm` : laser.id, channel)}
    </a>
    <div class="ml-auto flex items-center gap-1">
      <span
        class="flex size-3 shrink-0 items-center justify-center"
        title={busy && showPending ? pendingLabel : undefined}
      >
        {#if busy && showPending}
          <span role="status" aria-label={pendingLabel}><Loader2 class="size-3 animate-spin text-fg-muted" /></span>
        {/if}
      </span>
      <div
        class={cn(
          'grid h-[calc(var(--ui-xs)*0.65+2px)] auto-cols-fr grid-flow-col overflow-hidden rounded-full border text-[10px] transition-colors duration-150',
          disabled || enabled ? 'border-line-faint' : 'border-control-line'
        )}
        role="radiogroup"
        aria-label="Modulation mode"
        title={enabled ? 'Disable output to change mode' : 'Modulation mode'}
      >
        {#each modes as mode (mode)}
          <label class="min-w-0 cursor-pointer border-r border-control-line last:border-r-0">
            <input
              type="radio"
              name={`${id}-mode`}
              value={mode}
              checked={laser.modulationMode?.value === mode}
              disabled={disabled || enabled}
              onchange={() => toastError(laser.setModulationMode(mode))}
              class="peer sr-only"
            />
            <span
              class="flex h-full items-center justify-center px-1 text-center text-fg-muted peer-checked:bg-element-selected peer-checked:text-fg peer-focus-visible:outline peer-focus-visible:outline-border-focused peer-disabled:cursor-not-allowed peer-enabled:hover:bg-element-hover"
              >{modeLabels[mode]}</span
            >
          </label>
        {/each}
      </div>
      <span title="Enable source and permit output; external modulation still controls emission">
        <Switch
          checked={enabled}
          {disabled}
          onCheckedChange={(on) => toastError(toggleOutput(on))}
          aria-label="Card output permission"
          size="xs"
        />
      </span>
    </div>
  </div>
  <div class="flex min-w-0 flex-col gap-2 px-2.5 pb-2">
    <svg
      viewBox="0 0 {W} 100"
      preserveAspectRatio="none"
      class="h-20 w-full min-w-0 overflow-hidden rounded-xs border border-line-muted"
      role="img"
      aria-label="Power history in milliwatts over the last minute"
    >
      {#each segments(laser.outputPowerHistory) as segment, index (index)}
        <polygon points={segment.area} fill={color} opacity="0.16" />
        <polyline
          points={segment.line}
          fill="none"
          stroke={color}
          stroke-width="0.5"
          vector-effect="non-scaling-stroke"
        />
      {/each}
      {#each segments(laser.sourcePowerHistory) as segment, index (index)}
        <polyline
          points={segment.line}
          fill="none"
          stroke="var(--color-fg-muted)"
          stroke-width="1"
          vector-effect="non-scaling-stroke"
        />
      {/each}
      {#each segments(laser.sourceSetpointHistory) as segment, index (index)}
        <polyline
          points={segment.line}
          fill="none"
          stroke="var(--color-fg)"
          stroke-width="1"
          stroke-dasharray="2 3"
          vector-effect="non-scaling-stroke"
        />
      {/each}
    </svg>
    <div
      class="focus-within:border-focused flex min-w-0 items-stretch overflow-hidden rounded-sm border border-control-line"
      role="group"
      aria-label="Source"
    >
      <span
        class="flex w-20 shrink-0 items-center justify-between gap-1 border-r border-control-line bg-element-bg px-1.5 text-[10px] text-fg-muted"
        >Source <LinkIndicator {instrument} deviceId={laser.id} property="source_power_setpoint_mw" /></span
      >
      {#if hasSourceSlider}
        <div
          class={cn(
            'relative h-[calc(var(--ui-xs)-2px)] min-w-0 flex-1 bg-[color-mix(in_srgb,var(--element-bg),black_12%)]/50',
            sourceDisabled && 'opacity-40'
          )}
          title={`Source setpoint: ${reading(source?.value)} mW`}
        >
          <svg
            viewBox="0 0 100 10"
            preserveAspectRatio="none"
            class="pointer-events-none absolute inset-0 h-full w-full"
          >
            <rect x="0" y="0" width={sourcePosition} height="10" fill="var(--color-fg)" opacity="0.04" />
          </svg>
          <input
            type="range"
            class="level-slider source-slider absolute inset-0 h-full w-full"
            style:--thumb-color="var(--color-fg)"
            aria-label="Source power setpoint"
            min={sourceMin}
            max={sourceMax}
            step={source instanceof NumericModel ? (source.step ?? 'any') : 1}
            value={sourceValue}
            disabled={sourceDisabled}
            oninput={(event) => setSource(Number(event.currentTarget.value))}
          />
        </div>
      {:else}<div class="flex-1 bg-element-bg"></div>{/if}
      <div class="w-20 shrink-0 border-l border-control-line [&>div]:px-2" title="Source setpoint">
        {@render setting('Source setpoint', laser.sourcePowerSetpoint, 'mW', false, true)}
      </div>
      <div
        class="flex h-[calc(var(--ui-xs)-2px)] w-20 shrink-0 items-center justify-end gap-1 border-l border-control-line bg-element-active px-1 font-mono text-[10px] tabular-nums"
        title="Source-reported power"
      >
        <span>{reading(laser.sourcePower?.value)}</span><span class="text-fg-muted">mW</span>
      </div>
    </div>
    <div
      class="focus-within:border-focused flex min-w-0 items-stretch overflow-hidden rounded-sm border border-control-line"
      role="group"
      aria-label="Output"
    >
      <span
        class="flex w-20 shrink-0 items-center justify-between gap-1 border-r border-control-line bg-element-bg px-1.5 text-[10px] text-fg-muted"
        >Output <LinkIndicator {instrument} deviceId={laser.id} property="output_level_percent" /></span
      >
      {#if level instanceof NumericModel || levelOptions.length > 0}
        <div
          class={cn(
            'relative h-[calc(var(--ui-xs)-2px)] min-w-0 flex-1 bg-[color-mix(in_srgb,var(--element-bg),black_12%)]',
            levelDisabled && 'opacity-40'
          )}
          title={laser.outputLevelActive
            ? `Output level: ${level?.value}%`
            : 'External analog modulation controls intensity'}
        >
          <svg
            viewBox="0 0 100 10"
            preserveAspectRatio="none"
            class="pointer-events-none absolute inset-0 h-full w-full"
          >
            <!-- Optional fill; comment out this rectangle to compare without it. -->
            <rect x="0" y="0" width={levelPosition} height="10" fill={color} opacity="0.08" />
          </svg>
          <input
            type="range"
            class="level-slider absolute inset-0 h-full w-full"
            style:--thumb-color={color}
            aria-label="Output level percent"
            min={sliderMin}
            max={sliderMax}
            step={level instanceof NumericModel ? (level.step ?? 'any') : 1}
            value={sliderValue}
            disabled={levelDisabled}
            oninput={(event) => setLevel(Number(event.currentTarget.value))}
          />
        </div>
      {/if}
      <div class="w-20 shrink-0 border-l border-control-line [&>div]:px-2">
        {@render setting('Output level percent', laser.outputLevel, '%', !laser.outputLevelActive, true)}
      </div>
      <div
        class="flex h-[calc(var(--ui-xs)-2px)] w-20 shrink-0 items-center justify-end gap-1 border-l border-control-line bg-element-active px-1 font-mono text-[10px] tabular-nums"
        title="Measured output"
        aria-label="Measured output"
      >
        <span>{reading(laser.outputPower?.value)}</span><span class="text-fg-muted">mW</span>
      </div>
    </div>
  </div>
</div>

<style>
  .level-slider {
    appearance: none;
    -webkit-appearance: none;
    margin: 0;
    background: transparent;
    cursor: ew-resize;
  }
  .level-slider::-webkit-slider-runnable-track {
    height: 100%;
    background: transparent;
  }
  .level-slider::-moz-range-track {
    background: transparent;
  }
  .level-slider::-webkit-slider-thumb {
    appearance: none;
    -webkit-appearance: none;
    box-sizing: border-box;
    width: 2px;
    height: calc(var(--ui-xs) - 2px);
    margin-top: 0;
    border: none;
    border-radius: 0;
    background: linear-gradient(to right, var(--thumb-color) 0 1px, var(--color-fg) 1px 2px);
  }
  .level-slider::-moz-range-thumb {
    box-sizing: border-box;
    width: 2px;
    height: calc(var(--ui-xs) - 2px);
    border: none;
    border-radius: 0;
    background: linear-gradient(to right, var(--thumb-color) 0 1px, var(--color-fg) 1px 2px);
  }
  .source-slider::-webkit-slider-thumb {
    width: 1px;
  }
  .source-slider::-moz-range-thumb {
    width: 1px;
  }
  .level-slider:disabled {
    cursor: not-allowed;
  }
</style>
