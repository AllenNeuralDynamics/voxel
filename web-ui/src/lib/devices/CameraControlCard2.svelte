<script lang="ts">
  import { resolve } from '$app/paths';
  import { type CameraHandle, type Instrument } from '$lib/model';
  import LinkIndicator from '$lib/prop/LinkIndicator.svelte';
  import { Input } from '$lib/prop/numeric';
  import { cn, displayName } from '$lib/utils';

  let {
    camera,
    instrument,
    embedded = false
  }: { camera: CameraHandle; instrument: Instrument; embedded?: boolean } = $props();
  const channel = $derived(instrument.activeChannels.find((channel) => channel.camera.id === camera.id));
  const exposure = $derived(camera.exposure);
  const minimum = $derived(exposure?.min);
  const maximum = $derived(exposure?.max);
  const hasRange = $derived(
    minimum != null && maximum != null && Number.isFinite(minimum) && Number.isFinite(maximum) && maximum > minimum
  );
  const disabled = $derived(
    !camera.connected ||
      Boolean(camera.error) ||
      instrument.mode === 'capture' ||
      camera.getProp('exposure_time_ms')?.access !== 'rw' ||
      !exposure ||
      exposure.disabled
  );
  const position = $derived(
    hasRange && exposure ? Math.max(0, Math.min(100, ((exposure.value - minimum!) / (maximum! - minimum!)) * 100)) : 0
  );
  const streaming = $derived(camera.mode === 'PREVIEW' || camera.mode === 'ACQUISITION');
  const idle = $derived(camera.connected && !camera.error && camera.mode === 'IDLE');
  const info = $derived(camera.connected && !camera.error && streaming ? camera.streamInfo : undefined);
  const frame = $derived(camera.connected ? camera.frameSizePx : null);
  const sizeMb = $derived(camera.connected ? camera.frameSizeMb?.value : undefined);
  const buffer = $derived(info ? camera.bufferFill : null);
  const bufferPercent = $derived(buffer == null ? null : Math.max(0, Math.min(100, buffer * 100)));
  const status = $derived(
    !camera.connected
      ? 'Disconnected'
      : camera.error
        ? 'Error'
        : camera.mode
          ? displayName(camera.mode.toLowerCase())
          : 'Unknown'
  );

  function reading(value: number | null | undefined, decimals = 1): string {
    return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(decimals) : '—';
  }

  function liveReading(value: number | null | undefined, decimals = 1): string {
    return idle ? '' : reading(value, decimals);
  }
</script>

{#snippet statusIndicator()}
  <span
    class="flex w-5 shrink-0 items-center justify-center"
    role="img"
    aria-label={status}
    title={camera.error || status}
  >
    <span
      class={cn(
        'size-2 rounded-full',
        !camera.connected
          ? 'bg-fg-faint'
          : camera.error
            ? 'bg-danger'
            : camera.mode === 'PREVIEW'
              ? 'bg-success'
              : camera.mode === 'ACQUISITION'
                ? 'bg-warning'
                : 'bg-fg-muted/40'
      )}
    ></span>
  </span>
{/snippet}

{#snippet frameInfo()}
  <div
    class={cn(
      'grid min-w-0 overflow-hidden rounded-sm border border-control-line bg-element-bg font-mono text-[10px] tabular-nums',
      embedded
        ? 'shrink-0 grid-cols-[minmax(0,1fr)_4.5rem_1.5rem]'
        : 'grid-cols-[minmax(0,1fr)_calc(var(--spacing)*24)]'
    )}
  >
    <span class="flex h-6 min-w-0 items-center gap-1 px-1.5" title="Frame dimensions">
      <span class="truncate">{frame ? `${frame.x} × ${frame.y}` : '— × —'}</span>
      <span class="text-fg-muted">px</span>
    </span>
    <span class="flex h-6 items-center justify-end gap-1 border-l border-control-line px-1.5" title="Frame size">
      <span class="truncate">{reading(sizeMb)}</span><span class="text-fg-muted">MB</span>
    </span>
    {#if embedded}
      <span class="flex items-center justify-center border-l border-control-line">
        {@render statusIndicator()}
      </span>
    {/if}
  </div>
{/snippet}

<section
  class={cn('flex min-w-0 flex-col overflow-hidden', !embedded && 'rounded-lg border border-line-muted')}
  aria-label={`${displayName(camera.id)} control card 2`}
>
  {#if !embedded}
    <header class="flex h-9 min-w-0 items-center gap-2 px-2.5">
      <a
        href={resolve('/stations/[stationId]/instruments/[instrumentId]/devices/[deviceId]', {
          stationId: instrument.stationId,
          instrumentId: instrument.id,
          deviceId: camera.id
        })}
        class="min-w-0 flex-1 truncate rounded-sm text-base text-fg/80 hover:underline focus-visible:outline-2 focus-visible:outline-border-focused"
        title={channel
          ? `${displayName(camera.id)} — ${channel.label || displayName(channel.id)}`
          : displayName(camera.id)}
        >{displayName(camera.id)}{#if channel}<span class="ml-2 text-[10px] text-fg-muted"
            >{channel.label || displayName(channel.id)}</span
          >{/if}</a
      >
      <div
        class="flex h-5 shrink-0 divide-x divide-control-line overflow-hidden rounded-sm border border-control-line bg-element-bg font-mono text-[10px] tabular-nums"
      >
        {@render statusIndicator()}
      </div>
    </header>
  {:else}
    <header class="flex min-w-0 items-center justify-between gap-2 px-2.5 pb-2">
      <div class="flex min-w-0 flex-1 items-center gap-1 text-sm text-fg-muted">
        <span class="shrink-0">Camera:</span>
        <a
          href={resolve('/stations/[stationId]/instruments/[instrumentId]/devices/[deviceId]', {
            stationId: instrument.stationId,
            instrumentId: instrument.id,
            deviceId: camera.id
          })}
          class="min-w-0 truncate rounded-sm hover:text-fg hover:underline focus-visible:outline-2 focus-visible:outline-border-focused"
          title={displayName(camera.id)}>{displayName(camera.id)}</a
        >
      </div>
      {@render frameInfo()}
    </header>
  {/if}

  <div class="px-2.5 pb-2">
    <div
      class="focus-within:border-focused flex h-[calc(var(--ui-xs)-2px)] min-w-0 items-stretch overflow-hidden rounded-sm border border-control-line"
      role="group"
      aria-label="Exposure"
    >
      <span
        class="flex w-20 shrink-0 items-center justify-between gap-1 border-r border-control-line bg-element-bg px-1.5 text-[10px] text-fg-muted"
        >Exposure <LinkIndicator {instrument} deviceId={camera.id} property="exposure_time_ms" /></span
      >
      <div class={cn('relative min-w-0 flex-1 bg-element-bg/50', disabled && 'opacity-40')}>
        {#if hasRange && exposure}
          <div class="pointer-events-none absolute inset-y-0 left-0 bg-fg/5" style:width={`${position}%`}></div>
          <input
            type="range"
            class="exposure-slider absolute inset-0 h-full w-full"
            aria-label="Exposure time"
            min={minimum!}
            max={maximum!}
            step={exposure.step ?? 'any'}
            value={exposure.value}
            {disabled}
            oninput={(event) => exposure?.patch(Number(event.currentTarget.value), { throttled: true })}
          />
        {/if}
      </div>
      <div
        class="flex w-24 shrink-0 items-center gap-1 border-l border-control-line bg-element-bg px-2 font-mono text-[10px] tabular-nums"
      >
        {#if exposure}
          <Input
            model={exposure}
            {disabled}
            significantDigits={5}
            align="right"
            aria-label="Exposure time in milliseconds"
            class="min-w-0 flex-1 border-0 px-0 text-[10px]"
          />
        {:else}<span class="min-w-0 flex-1 text-right text-fg-muted">—</span>{/if}
        <span class="text-fg-muted">ms</span>
      </div>
    </div>
  </div>

  <div class="space-y-2 px-2.5 pb-2.5">
    {#if !embedded}{@render frameInfo()}{/if}
    <div
      class="grid grid-cols-[minmax(0,2.35fr)_minmax(0,0.8fr)_minmax(0,1.05fr)] divide-x divide-control-line overflow-hidden rounded-sm border border-control-line bg-element-bg font-mono text-[10px] tabular-nums"
      role="group"
      aria-label="Live capture telemetry"
    >
      <div class="flex h-6 min-w-0 items-center justify-between gap-1 px-1">
        <div class="flex min-w-0 flex-1 items-center gap-0.5" title="Capture buffer fill">
          <span class="mr-1 shrink-0 font-sans text-fg-muted">Buffer</span>
          <div
            class={cn('flex h-1.5 min-w-0 flex-1 gap-px', idle && 'invisible')}
            role="progressbar"
            aria-label="Capture buffer fill"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={bufferPercent ?? undefined}
            aria-valuetext={idle ? 'Idle' : bufferPercent == null ? 'Unavailable' : `${reading(bufferPercent, 0)}%`}
          >
            {#each [0, 1, 2, 3, 4] as tick (tick)}
              <span class="relative min-w-0 flex-1 overflow-hidden rounded-[1px] bg-fg/10">
                <span
                  class="absolute inset-y-0 left-0 bg-fg/40"
                  style:width={`${Math.max(0, Math.min(100, ((bufferPercent ?? 0) - tick * 20) * 5))}%`}
                ></span>
              </span>
            {/each}
          </div>
          <span class="flex w-[4.5ch] shrink-0 items-center justify-end gap-0.5"
            ><span>{liveReading(bufferPercent, 0)}</span><span class={cn('text-fg-muted', idle && 'invisible')}>%</span
            ></span
          >
        </div>
        <span class="flex w-[9ch] shrink-0 items-center justify-end gap-0.5" title="Dropped frames">
          <span class={cn('truncate', (info?.dropped_frames ?? 0) > 0 && 'text-danger')}
            >{liveReading(info?.dropped_frames, 0)}</span
          >
          <span class={cn('text-fg-muted', idle && 'invisible')}>dropped</span>
        </span>
      </div>
      <span class="flex h-6 min-w-0 items-center justify-end gap-0.5 px-1" title="Measured frame rate">
        <span class="truncate">{liveReading(info?.frame_rate_fps)}</span><span class="text-fg-muted">fps</span>
      </span>
      <span class="flex h-6 min-w-0 items-center justify-end gap-0.5 bg-element-active px-1" title="Measured data rate">
        <span class="truncate">{liveReading(info?.data_rate_mbs)}</span><span class="text-fg-muted">MB/s</span>
      </span>
    </div>
  </div>
</section>

<style>
  .exposure-slider {
    appearance: none;
    margin: 0;
    background: transparent;
    cursor: ew-resize;
    outline: none;
  }
  .exposure-slider:disabled {
    cursor: not-allowed;
  }
  .exposure-slider::-webkit-slider-runnable-track {
    height: 100%;
    background: transparent;
  }
  .exposure-slider::-webkit-slider-thumb {
    appearance: none;
    width: 1px;
    height: 100%;
    border: 0;
    border-radius: 0;
    background: var(--color-fg);
  }
  .exposure-slider::-moz-range-track {
    height: 100%;
    background: transparent;
  }
  .exposure-slider::-moz-range-thumb {
    width: 1px;
    height: 100%;
    border: 0;
    border-radius: 0;
    background: var(--color-fg);
  }
</style>
