<script lang="ts">
  import { ChevronDown } from '$lib/icons';
  import { Button } from '$lib/kit';
  import Switch from '$lib/kit/Switch.svelte';
  import { type Instrument, LaserHandle } from '$lib/model';
  import { cn, toastError } from '$lib/utils';

  interface Props {
    instrument: Instrument;
    class?: string;
  }

  let { instrument, class: className }: Props = $props();

  // Graph geometry: arbitrary viewBox width (stretched to fit) and the rolling time window.
  const W = 1000;
  const WINDOW_MS = LaserHandle.HISTORY_WINDOW_MS;

  const allLasers = $derived([...instrument.lasers.values()]);

  /** True when the laser is the illumination of a channel in the active profile. */
  const inProfile = (laserId: string): boolean => instrument.activeChannels.some((c) => c.laser.id === laserId);
  const profileLasers = $derived(allLasers.filter((l) => inProfile(l.id)));
  const otherLasers = $derived(allLasers.filter((l) => !inProfile(l.id)));

  const anyEnabled = $derived(allLasers.some((l) => l.isEnabled?.value === true));

  let profileCollapsed = $state(false);
  let othersCollapsed = $state(false);

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
</script>

<div class={cn('flex w-full min-w-68 flex-col bg-surface/50 py-2', className)}>
  <div class="flex shrink-0 items-center gap-2 px-3">
    <span class="text-xs font-medium tracking-wide text-fg-muted uppercase">Lasers</span>
    <div class="flex-1"></div>
    <Button variant="secondary" size="xs" disabled={!anyEnabled} onclick={stopAll}>Stop all</Button>
  </div>

  <div class="flex flex-col gap-4 py-3">
    {#if profileLasers.length > 0}
      {@render group('Profile lasers', profileLasers, profileCollapsed, () => (profileCollapsed = !profileCollapsed))}
    {/if}
    {#if otherLasers.length > 0}
      {@render group('Other Lasers', otherLasers, othersCollapsed, () => (othersCollapsed = !othersCollapsed))}
    {/if}
    {#if allLasers.length === 0}
      <p class="text-xs text-fg-muted/60">No lasers.</p>
    {/if}
  </div>
</div>

{#snippet group(title: string, lasers: LaserHandle[], collapsed: boolean, onToggle: () => void)}
  <div class="flex flex-col gap-1 px-3">
    <button
      class="flex w-full items-center gap-2 text-fg-muted/70 transition-colors hover:text-fg-muted"
      onclick={onToggle}
    >
      <span class="text-xs font-medium tracking-wide uppercase">{title}</span>
      <div class="flex-1"></div>
      {#if collapsed}
        <div class="flex items-center gap-1">
          {#each lasers as laser (laser.id)}
            {@render laserDot(laser)}
          {/each}
        </div>
      {/if}
      <ChevronDown class="h-3.5 w-3.5 shrink-0 transition-transform {collapsed ? '-rotate-90' : ''}" />
    </button>
    {#if !collapsed}
      <div class="flex flex-col gap-4">
        {#each lasers as laser (laser.id)}
          {@render laserRow(laser)}
        {/each}
      </div>
    {/if}
  </div>
{/snippet}

{#snippet laserDot(laser: LaserHandle)}
  {@const enabled = laser.isEnabled?.value === true}
  <div class="relative">
    {#if enabled}
      <div class="h-2 w-2 rounded-full" style="background-color: {laser.color};"></div>
      <span class="absolute inset-0 animate-ping rounded-full opacity-75" style="background-color: {laser.color};"
      ></span>
    {:else}
      <div class="h-2 w-2 rounded-full border opacity-70" style="border-color: {laser.color};"></div>
    {/if}
  </div>
{/snippet}

{#snippet laserRow(laser: LaserHandle)}
  {@const setpoint = laser.powerSetpoint?.value}
  {@const measured = laser.power?.value}
  {@const wl = laser.wavelength?.value}
  {@const temp = laser.temperature?.value}
  {@const enabled = laser.isEnabled?.value === true}
  <div class="flex flex-col gap-1">
    <div class="flex items-center gap-2 pt-1">
      <span class="text-xs font-medium tabular-nums">{wl ? `${wl} nm` : laser.id}</span>
      <div class="flex-1"></div>
      <span class="font-mono text-[10px] text-fg-muted tabular-nums">
        {typeof measured === 'number' ? measured.toFixed(1) : '—'} / {typeof setpoint === 'number'
          ? setpoint.toFixed(0)
          : '—'} mW{#if typeof temp === 'number'}
          · {temp.toFixed(1)} °C{/if}
      </span>
      <Switch class="shrink-0" checked={enabled} onCheckedChange={() => toastError(laser.toggle())} size="xs" />
    </div>

    <div
      class="flex h-12 overflow-hidden border border-border bg-canvas"
      {@attach laser.powerSetpoint?.wheel ?? (() => {})}
    >
      <div class="min-w-0 flex-1">
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
  <div class="relative h-full w-6 shrink-0 bg-card">
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
      {@const line = power.map((s) => `${toX(s.t)},${toY(s.v)}`).join(' ')}
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
      {@const line = setpoint.map((s) => `${toX(s.t)},${toY(s.v)}`).join(' ')}
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
