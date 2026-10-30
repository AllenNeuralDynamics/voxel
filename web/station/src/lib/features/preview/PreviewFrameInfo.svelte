<script lang="ts">
  import { prefersReducedMotion } from 'svelte/motion';

  import type { ColormapCatalog, PreviewViewport } from '$lib/core/model/types';
  import { prefs } from '$lib/core/prefs';
  import { cn } from '$lib/core/utils';
  import { Button, RadioBar } from '$lib/kit';
  import { Pause, Play } from '$lib/kit/icons';
  import { legibleFor, toHex } from '$lib/kit/themes/colors';
  import { themes } from '$lib/kit/themes/manager.svelte';

  import { FRAME_HISTORY_MS, frameRate } from './arrivals';
  import { isFullViewport, resolveColormapColor, toDisplayViewport, viewportFrameCovers } from './render';
  import type { PreviewChannel, PreviewFrameMetadata, PreviewSession } from './session.svelte';

  interface Props {
    previewer: PreviewSession | null;
    /** Moves the sparks. Turn it off while the panel is hidden. */
    active?: boolean;
    class?: string;
  }

  let { previewer, active = true, class: className }: Props = $props();

  interface ImageMap {
    /** Width over height of the camera image, as the preview shows it. */
    aspect: number;
    /** The detail frame, when it covers the view. Otherwise the view shows the overview. */
    detailFrame: PreviewFrameMetadata | null;
    /** Parts of the shown image, from 0 to 1. `view` is null while the view shows the whole image. */
    detail: PreviewViewport | null;
    view: PreviewViewport | null;
  }

  /** The time spans of a lane, in ms. The session keeps arrivals for the longest. */
  const SPANS = [10_000, 30_000, FRAME_HISTORY_MS];
  /** The most sparks in a lane. A lane is about this many pixels wide, so more sparks would only overlap. */
  const SPARK_STEPS = 1000;

  const span = prefs.centerPanel.framesSpan;
  const spanMs = $derived(SPANS.includes(span.get()) ? span.get() : SPANS[0]);
  /** The clock time of the pause, while the sparks are paused. */
  let pausedAt = $state<string | null>(null);
  let now = $state(performance.now());

  $effect(() => {
    if (!active || pausedAt) return;
    now = performance.now();
    // With reduced motion, the sparks step once a second instead of gliding.
    if (prefersReducedMotion.current) {
      const timer = setInterval(() => (now = performance.now()), 1000);
      return () => clearInterval(timer);
    }
    let frame = requestAnimationFrame(function tick() {
      now = performance.now();
      frame = requestAnimationFrame(tick);
    });
    return () => cancelAnimationFrame(frame);
  });

  const rows = $derived.by(() => {
    if (!previewer) return [];
    const catalog = previewer.catalog;
    return previewer.channels
      .filter((channel) => channel.name)
      .map((channel) => ({ channel, color: markColor(channel.resolvedColormap, catalog) }));
  });

  /** The brightest color of the channel's colormap, made light or dark enough to read on this theme. */
  function markColor(colormap: string | null, catalog: ColormapCatalog): string | undefined {
    const color = resolveColormapColor(colormap, catalog);
    return color ? legibleFor(toHex(color), themes.resolvedMode) : undefined;
  }

  function spanLabel(ms: number): string {
    return ms >= 60_000 ? `${ms / 60_000} min` : `${ms / 1000} s`;
  }

  function togglePause(): void {
    pausedAt = pausedAt
      ? null
      : new Date().toLocaleTimeString(undefined, {
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          hour12: false
        });
  }

  /** 1 spark for each arrival in the span, with x from 0 to SPARK_STEPS across the lane. */
  function sparks(times: readonly number[], now: number, span: number): string {
    const start = now - span;
    let path = '';
    let previous = -1;
    for (const at of times) {
      if (at < start) continue;
      const x = Math.round(((at - start) / span) * SPARK_STEPS);
      if (x === previous) continue;
      previous = x;
      path += `M${x} 1V0`;
    }
    return path;
  }

  /** Whole numbers from 9.5 up, so a camera at 10 fps does not flicker between "9.9" and "10". */
  function formatRate(rate: number): string {
    return rate < 9.5 ? rate.toFixed(1) : String(Math.round(rate));
  }

  function imageMap(channel: PreviewChannel, viewport: PreviewViewport): ImageMap {
    const turned = Math.abs(Math.round(channel.rotationDeg / 90)) % 2 === 1;
    const width = channel.sensorWidth || 1;
    const height = channel.sensorHeight || 1;
    const frame = channel.viewportFrame;
    const detailFrame = frame && viewportFrameCovers(frame, viewport, channel.rotationDeg) ? frame : null;
    return {
      aspect: turned ? height / width : width / height,
      detailFrame,
      detail: detailFrame ? toDisplayViewport(imagePart(detailFrame), channel.rotationDeg) : null,
      view: isFullViewport(viewport) ? null : viewport
    };
  }

  function imagePart(frame: PreviewFrameMetadata): PreviewViewport {
    const rect = frame.source_rect_px;
    return {
      x: rect.x / frame.sensor_width,
      y: rect.y / frame.sensor_height,
      w: rect.width / frame.sensor_width,
      h: rect.height / frame.sensor_height
    };
  }

  /** The part of the camera image that the frame shows, in camera pixels. */
  function cameraSize(frame: PreviewFrameMetadata): string {
    return `${frame.source_rect_px.width} × ${frame.source_rect_px.height}`;
  }

  /** The frame that the preview sent, in its own pixels. */
  function previewSize(frame: PreviewFrameMetadata): string {
    return `${frame.width} × ${frame.height}`;
  }
</script>

{#snippet lane(times: readonly number[], color: string | undefined)}
  <svg
    class="block w-full overflow-visible"
    style:height="calc(var(--line-h) * 0.75)"
    viewBox="0 0 {SPARK_STEPS} 1"
    preserveAspectRatio="none"
    style:color
    aria-hidden="true"
  >
    <path d="M0 1H{SPARK_STEPS}" class="nss stroke-line-faint" />
    <path d={sparks(times, now, spanMs)} class="nss" stroke="currentColor" />
  </svg>
{/snippet}

{#snippet sizes(frame: PreviewFrameMetadata)}
  {@const title = `${cameraSize(frame)} camera pixels, sent as ${previewSize(frame)}`}
  <dd class="camera-size px-2 text-right whitespace-nowrap text-fg" aria-hidden="true" {title}>{cameraSize(frame)}</dd>
  <dd class="size-arrow text-fg-faint" aria-hidden="true" {title}>→</dd>
  <dd class="col-start-4 px-2 whitespace-nowrap text-fg" {title}>
    <span class="sr-only">{cameraSize(frame)} sent as</span>
    {previewSize(frame)}
  </dd>
{/snippet}

<div
  class={cn(
    '@container-size grid h-full min-h-0 grid-cols-[repeat(6,max-content)_minmax(0,1fr)_max-content] grid-rows-[auto_minmax(0,1fr)] overflow-hidden',
    className
  )}
  style="--row-h: clamp(3rem, calc((100cqh - 3rem - 2px) / var(--rows)), 5.5rem); --line-h: calc((var(--row-h) - 0.6rem) / 2); --map-h: calc((var(--row-h) - 0.9rem) * 0.85)"
  style:--rows={rows.length}
>
  <div class="col-span-full grid h-8 grid-cols-subgrid items-center">
    <div class="col-span-6 flex px-2">
      <RadioBar
        value={spanMs}
        options={SPANS}
        formatLabel={spanLabel}
        onChange={(value) => span.set(value)}
        size="xs"
        aria-label="Time span"
      />
    </div>
    <div class="flex justify-between gap-2 px-2 text-sm text-fg-faint" aria-hidden="true">
      <span>{spanLabel(spanMs)} ago</span>
      <span>{pausedAt ?? 'Now'}</span>
    </div>
    <div class="flex justify-end px-2">
      <Button variant="quiet" size="xs" onclick={togglePause}>
        {#if pausedAt}
          <Play class="size-3.5" aria-hidden="true" />Resume
        {:else}
          <Pause class="size-3.5" aria-hidden="true" />Pause
        {/if}
      </Button>
    </div>
  </div>
  {#if !previewer || rows.length === 0}
    <p class="col-span-full bottom-panel-box flex items-center justify-center text-fg-muted">No preview.</p>
  {:else}
    {@const viewport = previewer.viewport}
    <div class="col-span-full bottom-panel-box grid grid-cols-subgrid content-start">
      {#each rows as { channel, color } (channel.idx)}
        {@const map = imageMap(channel, viewport)}
        {@const rate = frameRate(channel.arrivals.overview, now)}
        <div
          class="col-span-full grid grid-cols-subgrid items-center border-t border-line-faint first:border-t-0"
          style:height="var(--row-h)"
          role="group"
          aria-label={channel.label}
        >
          <span class="line-clamp-2 max-w-24 px-2 wrap-anywhere text-fg" title={channel.label}>{channel.label}</span>
          <span class="px-2" title={map.view ? 'Dashed box: your view' : undefined}>
            <svg
              class="block max-w-28 overflow-visible"
              style:height="var(--map-h)"
              style:width="calc(var(--map-h) * {map.aspect})"
              style:color
              viewBox="0 0 {100 * map.aspect} 100"
              aria-hidden="true"
            >
              <rect
                width={100 * map.aspect}
                height="100"
                class="nss stroke-line"
                fill="currentColor"
                fill-opacity={channel.overviewFrame ? 0.15 : 0}
              />
              {#if map.detail}
                <!-- The stroke keeps a small part visible at high zoom. -->
                <rect
                  x={map.detail.x * 100 * map.aspect}
                  y={map.detail.y * 100}
                  width={map.detail.w * 100 * map.aspect}
                  height={map.detail.h * 100}
                  class="nss"
                  fill="currentColor"
                  stroke="currentColor"
                  stroke-width="2"
                />
              {/if}
              {#if map.view}
                <rect
                  x={map.view.x * 100 * map.aspect}
                  y={map.view.y * 100}
                  width={map.view.w * 100 * map.aspect}
                  height={map.view.h * 100}
                  class="nss stroke-fg"
                  fill="none"
                  stroke-dasharray="3 2"
                />
              {/if}
            </svg>
          </span>
          <dl class="col-span-6 grid auto-rows-(--line-h) grid-cols-subgrid items-center tabular-nums">
            <dt class="col-start-1 px-2 text-fg-muted">Overview</dt>
            {#if channel.overviewFrame}
              {@render sizes(channel.overviewFrame)}
            {:else}
              <dd class="col-span-3 px-2 text-fg-muted">—</dd>
            {/if}
            <dd class="px-2">{@render lane(channel.arrivals.overview, color)}</dd>
            <dd class="px-2 text-right whitespace-nowrap text-fg-muted">
              {#if typeof rate === 'number'}
                <span class="font-mono text-fg">{formatRate(rate)}</span> fps
              {:else}
                {rate === 'stopped' ? 'Stopped' : '—'}
              {/if}
            </dd>
            <dt class="col-start-1 px-2 text-fg-muted">Detail</dt>
            {#if map.detailFrame}
              {@render sizes(map.detailFrame)}
            {:else}
              <dd class="col-span-3 px-2 whitespace-nowrap text-fg-muted">{map.view ? '—' : 'Not zoomed'}</dd>
            {/if}
            <dd class="px-2">{@render lane(channel.arrivals.viewport, color)}</dd>
          </dl>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  /* On a narrow panel, only the sent size shows, so the lanes keep their room. Its title still gives both sizes. */
  @container (max-width: 64rem) {
    .camera-size,
    .size-arrow {
      display: none;
    }
  }
</style>
