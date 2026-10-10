<script lang="ts">
  import { Button } from '$lib/kit';
  import Switch from '$lib/kit/Switch.svelte';
  import { EnumeratedModel, type Instrument, LaserHandle, type LaserSample, NumericModel } from '$lib/model';
  import { PropInput } from '$lib/prop';
  import * as Numeric from '$lib/prop/numeric';
  import { cn, toastError } from '$lib/utils';

  import DeckHeader from './DeckHeader.svelte';
  import { deviceIdentity } from './snippets.svelte';

  interface Props {
    instrument: Instrument;
    class?: string;
  }

  let { instrument, class: className }: Props = $props();

  // Graph geometry: arbitrary viewBox width (stretched to fit) and the rolling time window.
  const W = 1000;
  const WINDOW_MS = 60_000;

  const allLasers = $derived([...instrument.lasers.values()]);

  /** The active-profile channel this laser illuminates, if any. */
  const channelOf = (laserId: string) => instrument.activeChannels.find((c) => c.laser.id === laserId);

  // In-profile lasers first (what the active profile drives), then the rest — profile tiles carry a channel chip.
  const sortedLasers = $derived([
    ...allLasers.filter((l) => channelOf(l.id) !== undefined),
    ...allLasers.filter((l) => channelOf(l.id) === undefined)
  ]);

  const anyEnabled = $derived(allLasers.some((l) => l.outputEnabled?.value === true));

  // Smooth-scroll ticker: advance the graphs' right edge each frame. Recording itself is stream-driven
  // in LaserHandle, so history keeps filling even while this component is unmounted; only the scroll pauses.
  let now = $state(performance.now());
  $effect(() => {
    let raf = 0;
    const tick = (): void => {
      now = performance.now();
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  });

  function stopAll(): void {
    for (const laser of allLasers) {
      if (laser.outputEnabled?.value === true) toastError(laser.disableOutput());
    }
  }

  function sourceScale(laser: LaserHandle): number {
    const model = laser.sourcePowerSetpoint?.model;
    const maximum = model instanceof NumericModel ? model.max : null;
    const options =
      model instanceof EnumeratedModel ? model.options.filter((v): v is number => typeof v === 'number') : [];
    return Math.max(
      1,
      maximum ?? 0,
      ...options,
      ...laser.sourcePowerHistory.flatMap((sample) => (sample.v == null ? [] : [sample.v])),
      ...laser.sourceSetpointHistory.flatMap((sample) => (sample.v == null ? [] : [sample.v]))
    );
  }

  // Hold reported values until the next observation; unavailable readings break the line.
  function stepSegments(samples: LaserSample[], toX: (t: number) => string, toY: (v: number) => string): string[] {
    const segments: string[] = [];
    let points = '';
    let previous: number | null = null;
    for (const sample of samples) {
      if (previous != null) points += ` ${toX(sample.t)},${toY(previous)}`;
      if (sample.v == null) {
        if (points) segments.push(points);
        points = '';
      } else {
        points += ` ${toX(sample.t)},${toY(sample.v)}`;
      }
      previous = sample.v;
    }
    if (previous != null) segments.push(`${points} ${W},${toY(previous)}`);
    return segments;
  }
</script>

<div class={cn('flex w-full min-w-68 flex-col', className)}>
  <DeckHeader title="Lasers" count={allLasers.length}>
    {#snippet actions()}
      <Button
        variant="ghost"
        size="xs"
        disabled={!anyEnabled}
        class={cn('text-sm font-normal', anyEnabled ? 'text-danger' : 'opacity-50')}
        onclick={stopAll}
      >
        Stop all
      </Button>
    {/snippet}
  </DeckHeader>

  <div class="flex flex-col gap-4 px-3 pt-1 pb-3">
    {#if sortedLasers.length > 0}
      {#each sortedLasers as laser (laser.id)}
        {@render laserTile(laser)}
      {/each}
    {:else}
      <p class=" text-fg-muted">No lasers.</p>
    {/if}
  </div>
</div>

{#snippet laserTile(laser: LaserHandle)}
  {@const powerSetpoint = laser.sourcePowerSetpoint}
  {@const setpoint = powerSetpoint?.value}
  {@const numericSetpoint = powerSetpoint?.model instanceof NumericModel ? powerSetpoint.model : undefined}
  {@const powerUnits = powerSetpoint?.units || 'mW'}
  {@const measured = laser.sourcePower?.value}
  {@const wl = laser.wavelength?.value}
  <!-- {@const temp = laser.temperature?.value} -->
  {@const enabled = laser.outputEnabled?.value === true}
  {@const channel = channelOf(laser.id)}
  <div class="flex flex-col overflow-hidden rounded-xs border border-line bg-card">
    <!-- row 1: identity + power readout + enable -->
    <div class="flex items-center gap-3 px-2.5 pt-2 pb-1.5">
      {@render deviceIdentity(wl ? `${wl} nm` : laser.id, channel)}
      <span
        class="focus-within:border-focused ml-auto inline-flex shrink-0 items-stretch overflow-hidden rounded-sm border border-control-line font-mono text-[10px] tabular-nums transition-colors"
      >
        <span class="inline-flex items-center px-1.5" title="Source power setpoint">
          {#if numericSetpoint}
            <Numeric.Input
              model={numericSetpoint}
              disabled={numericSetpoint.disabled || powerSetpoint?.access !== 'rw'}
              numCharacters={4}
              align="left"
              aria-label={`${laser.id} source power setpoint (${powerUnits})`}
              class="min-w-[6ch] px-0.5 text-fg disabled:opacity-50"
            />
          {:else if powerSetpoint}
            <PropInput model={powerSetpoint.model} disabled={powerSetpoint.access !== 'rw'} size="xs" />
          {:else}
            <span class="w-[6ch] text-left text-fg-muted">—</span>
          {/if}
        </span>
        <span
          class="inline-flex items-center gap-1.5 border-l border-control-line bg-element-active px-1.5 text-fg"
          title="Source-reported power"
        >
          <span class="min-w-[6ch] text-left text-fg">{typeof measured === 'number' ? measured.toFixed(1) : '—'}</span>
          <span>{powerUnits}</span>
        </span>
      </span>
      <span title="Output permission; external modulation may still block light">
        <Switch
          class="shrink-0"
          checked={enabled}
          disabled={laser.isBusy || instrument.mode === 'capture' || (!enabled && laser.sourceEnabled?.value !== true)}
          onCheckedChange={(checked) => toastError(checked ? laser.enableOutput() : laser.disableOutput())}
          size="xs"
        />
      </span>
    </div>

    <!-- row 2: power graph + setpoint slider — full-bleed to the card edges, hairline dividers only -->
    <div class="flex h-10 border-t border-line-muted" {@attach numericSetpoint?.wheel ?? (() => {})}>
      <div class="min-w-0 flex-1">
        {@render graph(laser)}
      </div>
      {#if typeof setpoint === 'number' && numericSetpoint && numericSetpoint.min != null && numericSetpoint.max != null}
        {@const maxP = sourceScale(laser)}
        {@const py = typeof measured === 'number' ? 100 - (measured / maxP) * 100 : null}
        {@const sy = 100 - (setpoint / maxP) * 100}
        {@const color = laser.color ?? 'var(--color-fg-muted)'}
        <div class="w-5 shrink-0 border-l border-line-muted">
          <div class="relative h-full w-full">
            <svg
              viewBox="0 0 10 100"
              preserveAspectRatio="none"
              class="pointer-events-none absolute inset-0 h-full w-full"
            >
              {#if py != null}
                <rect x="0" y={py} width="10" height={100 - py} fill={color} opacity="0.3" />
                <line
                  x1="0"
                  y1={py}
                  x2="10"
                  y2={py}
                  stroke={color}
                  stroke-width="1"
                  vector-effect="non-scaling-stroke"
                />
              {/if}
              <line
                x1="0"
                y1={sy}
                x2="10"
                y2={sy}
                stroke={color}
                stroke-width="1"
                stroke-dasharray="4 3"
                vector-effect="non-scaling-stroke"
                opacity="0.8"
              />
            </svg>
            <input
              type="range"
              class="setpoint-slider absolute inset-0 z-10 h-full w-full"
              min={numericSetpoint.min}
              max={numericSetpoint.max}
              step={numericSetpoint.step ?? 'any'}
              value={setpoint}
              disabled={numericSetpoint.disabled || powerSetpoint?.access !== 'rw'}
              oninput={(e) => numericSetpoint.patch(parseFloat(e.currentTarget.value), { throttled: true })}
            />
          </div>
        </div>
      {/if}
    </div>
  </div>
{/snippet}

{#snippet graph(laser: LaserHandle)}
  {@const maxP = sourceScale(laser)}
  {@const color = laser.color ?? 'var(--color-fg-muted)'}
  {@const tStart = now - WINDOW_MS}
  {@const toX = (t: number) => (((t - tStart) / WINDOW_MS) * W).toFixed(1)}
  {@const toY = (v: number) => (100 - (v / maxP) * 100).toFixed(1)}
  {@const power = laser.sourcePowerHistory}
  {@const setpoint = laser.sourceSetpointHistory}
  <svg viewBox="0 0 {W} 100" preserveAspectRatio="none" class="h-full w-full">
    {#each stepSegments(power, toX, toY) as points, index (index)}
      <polyline {points} fill="none" stroke={color} stroke-width="1" vector-effect="non-scaling-stroke" />
    {/each}
    {#each stepSegments(setpoint, toX, toY) as points, index (index)}
      <polyline
        {points}
        fill="none"
        stroke={color}
        stroke-width="1"
        stroke-dasharray="4 3"
        vector-effect="non-scaling-stroke"
        opacity="0.8"
      />
    {/each}
  </svg>
{/snippet}

<style>
  .setpoint-slider {
    appearance: none;
    -webkit-appearance: none;
    writing-mode: vertical-rl;
    direction: rtl;
    margin: 0;
    background: transparent;
    cursor: pointer;
  }
  .setpoint-slider::-webkit-slider-runnable-track {
    background: transparent;
  }
  .setpoint-slider::-moz-range-track {
    background: transparent;
  }
  .setpoint-slider::-webkit-slider-thumb {
    appearance: none;
    -webkit-appearance: none;
    inline-size: 4px;
    block-size: 100%;
    background: transparent;
    cursor: pointer;
  }
  .setpoint-slider::-moz-range-thumb {
    appearance: none;
    inline-size: 4px;
    block-size: 100%;
    border: none;
    background: transparent;
    cursor: pointer;
  }
  .setpoint-slider:disabled,
  .setpoint-slider:disabled::-webkit-slider-thumb,
  .setpoint-slider:disabled::-moz-range-thumb {
    cursor: not-allowed;
  }
</style>
