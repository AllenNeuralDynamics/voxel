<script lang="ts">
  import { Button } from '$lib/kit';
  import Switch from '$lib/kit/Switch.svelte';
  import { type Instrument, LaserHandle } from '$lib/model';
  import { cn, toastError } from '$lib/utils';

  import { deviceIdentity } from './snippets.svelte';

  interface Props {
    instrument: Instrument;
    class?: string;
  }

  let { instrument, class: className }: Props = $props();

  // Graph geometry: arbitrary viewBox width (stretched to fit) and the rolling time window.
  const W = 1000;
  const WINDOW_MS = LaserHandle.HISTORY_WINDOW_MS;

  const allLasers = $derived([...instrument.lasers.values()]);

  /** The active-profile channel this laser illuminates, if any. */
  const channelOf = (laserId: string) => instrument.activeChannels.find((c) => c.laser.id === laserId);

  // In-profile lasers first (what the active profile drives), then the rest — profile rows carry a channel chip.
  const sortedLasers = $derived([
    ...allLasers.filter((l) => channelOf(l.id) !== undefined),
    ...allLasers.filter((l) => channelOf(l.id) === undefined)
  ]);

  const anyEnabled = $derived(allLasers.some((l) => l.isEnabled?.value === true));

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
      if (laser.isEnabled?.value === true) toastError(laser.disable());
    }
  }

  // Event-driven history is a sample-and-hold signal: a value stays put until the next event. Draw it as a
  // staircase — hold flat at (t_next, v_prev), then jump vertically to v_next — so a return to a prior level
  // reads as a square edge rather than a diagonal ramp across the idle gap.
  function stepPoints(
    samples: { t: number; v: number }[],
    toX: (t: number) => string,
    toY: (v: number) => string
  ): string {
    let pts = `${toX(samples[0].t)},${toY(samples[0].v)}`;
    for (let i = 1; i < samples.length; i++) {
      pts += ` ${toX(samples[i].t)},${toY(samples[i - 1].v)} ${toX(samples[i].t)},${toY(samples[i].v)}`;
    }
    return pts;
  }
</script>

<div class={cn('flex w-full min-w-68 flex-col py-2', className)}>
  <div class="flex shrink-0 items-center gap-2 px-3">
    <span class="text-xs font-medium tracking-wide text-fg-muted uppercase">Lasers</span>
    <div class="flex-1"></div>
    <Button variant="ghost" size="xs" disabled={!anyEnabled} onclick={stopAll}>Stop all</Button>
  </div>

  <div class="flex flex-col py-3">
    {#if sortedLasers.length > 0}
      <div class="flex flex-col divide-y divide-border">
        {#each sortedLasers as laser (laser.id)}
          {@render laserRow(laser)}
        {/each}
      </div>
    {:else}
      <p class="px-3 text-xs text-fg-muted/60">No lasers.</p>
    {/if}
  </div>
</div>

{#snippet laserRow(laser: LaserHandle)}
  {@const setpoint = laser.powerSetpoint?.value}
  {@const measured = laser.power?.value}
  {@const wl = laser.wavelength?.value}
  <!-- {@const temp = laser.temperature?.value} -->
  {@const enabled = laser.isEnabled?.value === true}
  {@const channel = channelOf(laser.id)}
  <div class="flex flex-col gap-1 px-3 py-3">
    <div class="flex items-center gap-2">
      {@render deviceIdentity(wl ? `${wl} nm` : laser.id, channel)}
      <div class="flex-1"></div>
      <span class="font-mono text-[10px] text-fg-muted tabular-nums">
        {typeof measured === 'number' ? measured.toFixed(1) : '—'} / {typeof setpoint === 'number'
          ? setpoint.toFixed(0)
          : '—'} mW<!--{#if typeof temp === 'number'}
          · {temp.toFixed(1)} °C{/if}-->
      </span>
      <Switch class="shrink-0" checked={enabled} onCheckedChange={() => toastError(laser.toggle())} size="xs" />
    </div>

    <div
      class="flex h-12 gap-1 overflow-hidden rounded border-0 border-border bg-canvas"
      {@attach laser.powerSetpoint?.wheel ?? (() => {})}
    >
      <div class="min-w-0 flex-1 rounded border border-border">
        {@render graph(laser)}
      </div>
      {#if typeof setpoint === 'number'}
        {@render setpointSlider(laser, setpoint)}
      {/if}
    </div>
  </div>
{/snippet}

{#snippet setpointSlider(laser: LaserHandle, setpoint: number)}
  {@const maxP = laser.maxPower || 1}
  {@const py = 100 - ((laser.power?.value ?? 0) / maxP) * 100}
  {@const sy = 100 - (setpoint / maxP) * 100}
  {@const color = laser.color ?? 'var(--color-fg-muted)'}
  <div class="relative h-full w-7 shrink-0 rounded-sm border border-border bg-card">
    <svg viewBox="0 0 10 100" preserveAspectRatio="none" class="pointer-events-none absolute inset-0 h-full w-full">
      <rect x="0" y={py} width="10" height={100 - py} fill={color} opacity="0.3" />
      <line x1="0" y1={py} x2="10" y2={py} stroke={color} stroke-width="1" vector-effect="non-scaling-stroke" />
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
      min={0}
      max={maxP}
      step={1}
      value={setpoint}
      oninput={(e) => laser.powerSetpoint?.patch(parseFloat(e.currentTarget.value), { throttled: true })}
    />
  </div>
{/snippet}

{#snippet graph(laser: LaserHandle)}
  {@const maxP = laser.maxPower || 1}
  {@const color = laser.color ?? 'var(--color-fg-muted)'}
  {@const tStart = now - WINDOW_MS}
  {@const toX = (t: number) => (((t - tStart) / WINDOW_MS) * W).toFixed(1)}
  {@const toY = (v: number) => (100 - (v / maxP) * 100).toFixed(1)}
  {@const power = laser.powerHistory}
  {@const setpoint = laser.setpointHistory}
  <svg viewBox="0 0 {W} 100" preserveAspectRatio="none" class="h-full w-full">
    {#if power.length > 0}
      {@const line = stepPoints(power, toX, toY)}
      {@const edgeY = toY(power[power.length - 1].v)}
      <polygon
        points="{toX(power[0].t)},100 {line} {W},{edgeY} {W},100"
        fill={color}
        fill-opacity="0.3"
        stroke="none"
      />
      <polyline
        points="{line} {W},{edgeY}"
        fill="none"
        stroke={color}
        stroke-width="1"
        vector-effect="non-scaling-stroke"
      />
    {/if}
    {#if setpoint.length > 0}
      {@const line = stepPoints(setpoint, toX, toY)}
      {@const edgeY = toY(setpoint[setpoint.length - 1].v)}
      <polyline
        points="{line} {W},{edgeY}"
        fill="none"
        stroke={color}
        stroke-width="1"
        stroke-dasharray="4 3"
        vector-effect="non-scaling-stroke"
        opacity="0.8"
      />
    {/if}
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
</style>
