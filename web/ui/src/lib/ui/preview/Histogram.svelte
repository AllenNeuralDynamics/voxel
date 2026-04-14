<script lang="ts">
  import { ContextMenu } from '$lib/ui/kit';
  import { computeAutoLevels } from '$lib/utils';
  import ColormapPicker from './ColormapPicker.svelte';
  import { EyeOff } from '$lib/icons';
  import type { ColormapCatalog } from '$lib/main';
  import { useEventListener } from 'runed';

  interface Props {
    label: string;
    histData: number[] | null;
    levelsMin: number;
    levelsMax: number;
    onLevelsChange: (min: number, max: number) => void;
    colormap: string | null;
    catalog: ColormapCatalog;
    onColormapChange: (colormap: string) => void;
    dataTypeMax?: number;
    visible?: boolean;
    onVisibilityChange?: (visible: boolean) => void;
  }

  let {
    label,
    histData,
    levelsMin,
    levelsMax,
    onLevelsChange,
    colormap,
    catalog,
    onColormapChange,
    dataTypeMax = 65535,
    visible,
    onVisibilityChange
  }: Props = $props();

  // ── Constants ─────────────────────────────────────────────────────

  const svgHeight = 20;
  const labelWidth = 36;
  const labelGap = 4;
  const gradientId = `ch-grad-${Array.from(crypto.getRandomValues(new Uint8Array(4)), (b) => b.toString(16).padStart(2, '0')).join('')}`;

  // ── State ─────────────────────────────────────────────────────────

  let windowMin = $state(0);
  let windowMax = $state(0);
  let hasAutoFit = $state(false);
  let svgWidth = $state(256);
  let columnWidth = $state(288);
  let dragging = $state<'min' | 'max' | null>(null);
  let histContainerEl = $state<HTMLElement | null>(null);

  // ── Derived: Domain ───────────────────────────────────────────────

  const colors = $derived.by(() => {
    if (!colormap) return ['#06b6d4'];
    if (colormap.startsWith('#')) return [colormap];
    for (const group of catalog) {
      const stops = group.colormaps[colormap];
      if (stops) return stops;
    }
    return ['#06b6d4'];
  });

  const hasValidData = $derived(!!histData && histData.length > 0);
  const numBins = $derived(histData?.length || 1);
  const startBin = $derived(Math.floor((windowMin / dataTypeMax) * (numBins - 1)));
  const endBin = $derived(Math.ceil((windowMax / dataTypeMax) * (numBins - 1)));
  const minIntensity = $derived(Math.round(levelsMin * dataTypeMax));
  const maxIntensity = $derived(Math.round(levelsMax * dataTypeMax));

  // ── Mapping: level ↔ pixel X ──────────────────────────────────────

  function levelToX(level: number): number {
    if (windowMax === windowMin) return 0;
    const intensity = level * dataTypeMax;
    return ((intensity - windowMin) / (windowMax - windowMin)) * svgWidth;
  }

  function xToLevel(clientX: number, rect: DOMRect): number {
    const x = Math.max(0, Math.min(svgWidth, clientX - rect.left));
    const rel = x / svgWidth;
    const intensity = windowMin + rel * (windowMax - windowMin);
    return intensity / dataTypeMax;
  }

  // ── Derived: Geometry ─────────────────────────────────────────────

  const minHandleX = $derived(Math.max(0, Math.min(svgWidth, levelToX(levelsMin))));
  const maxHandleX = $derived(Math.max(0, Math.min(svgWidth - 2, levelToX(levelsMax))));

  const displayHist = $derived.by(() => {
    if (!hasValidData || !histData) return [];
    const slice = histData.slice(startBin, endBin + 1);
    const peak = Math.max(...slice);
    if (peak === 0) return slice.map(() => 0);
    return slice.map((c) => c / peak);
  });

  const bgPoints = $derived.by(() => {
    if (displayHist.length === 0) return '';
    return displayHist
      .map((v, i) => {
        const x = (i / (displayHist.length - 1 || 1)) * svgWidth;
        const y = svgHeight - v * svgHeight;
        return `${x},${y}`;
      })
      .join(' ');
  });

  const fgEntries = $derived.by(() => {
    if (displayHist.length < 2) return [];
    const step = svgWidth / (displayHist.length - 1);
    const yAt = (x: number): number => {
      const fIdx = x / step;
      const i0 = Math.max(0, Math.min(displayHist.length - 1, Math.floor(fIdx)));
      const i1 = Math.min(i0 + 1, displayHist.length - 1);
      const t = fIdx - i0;
      const v = displayHist[i0] + (displayHist[i1] - displayHist[i0]) * t;
      return svgHeight - v * svgHeight;
    };
    const entries: { x: number; y: number }[] = [{ x: minHandleX, y: yAt(minHandleX) }];
    for (let i = 0; i < displayHist.length; i++) {
      const x = i * step;
      if (x > minHandleX && x < maxHandleX) {
        entries.push({ x, y: svgHeight - displayHist[i] * svgHeight });
      }
    }
    entries.push({ x: maxHandleX, y: yAt(maxHandleX) });
    return entries;
  });

  const fgPoints = $derived(fgEntries.map((p) => `${p.x},${p.y}`).join(' '));

  const fgPolygon = $derived.by(() => {
    if (fgEntries.length < 2) return '';
    const first = fgEntries[0];
    const last = fgEntries[fgEntries.length - 1];
    return `${first.x},${svgHeight} ${fgEntries.map((p) => `${p.x},${p.y}`).join(' ')} ${last.x},${svgHeight}`;
  });

  const labelPositions = $derived.by(() => {
    const containerW = svgWidth;

    // Position left edge at handle X; CSS margin handles the visual offset
    let minLeft = minHandleX;
    let maxLeft = maxHandleX;

    // Ensure they don't overlap
    const minDist = labelWidth + labelGap;
    if (maxLeft - minLeft < minDist) {
      const mid = (minLeft + maxLeft) / 2;
      minLeft = mid - minDist / 2;
      maxLeft = mid + minDist / 2;
    }

    // Shift pair into bounds
    if (minLeft < 0) {
      const shift = -minLeft;
      minLeft += shift;
      maxLeft += shift;
    }
    if (maxLeft > containerW - labelWidth) {
      const shift = maxLeft - (containerW - labelWidth);
      maxLeft -= shift;
      minLeft -= shift;
    }

    // Final safety clamp
    minLeft = Math.max(0, minLeft);
    maxLeft = Math.min(containerW - labelWidth, maxLeft);

    return { minLeft, maxLeft };
  });

  // ── Handlers: Drag ────────────────────────────────────────────────

  function onHandleDown(e: PointerEvent, handle: 'min' | 'max') {
    e.preventDefault();
    (e.currentTarget as SVGElement).setPointerCapture(e.pointerId);
    dragging = handle;
  }

  function onHandleMove(e: PointerEvent) {
    if (!dragging) return;
    const svg = (e.currentTarget as SVGElement).closest('svg');
    if (!svg) return;
    const level = xToLevel(e.clientX, svg.getBoundingClientRect());

    const minGap = 1 / dataTypeMax;
    if (dragging === 'min') {
      onLevelsChange(Math.max(0, Math.min(level, levelsMax - minGap)), levelsMax);
    } else {
      onLevelsChange(levelsMin, Math.min(1, Math.max(level, levelsMin + minGap)));
    }
  }

  function onHandleUp(e: PointerEvent) {
    (e.currentTarget as SVGElement).releasePointerCapture(e.pointerId);
    dragging = null;
  }

  // ── Handlers: Wheel Zoom ──────────────────────────────────────────

  function onHistWheel(e: WheelEvent) {
    e.preventDefault();

    const range = windowMax - windowMin;
    const zoomFactor = e.deltaY > 0 ? 1.15 : 0.85;
    const newRange = Math.max(range * zoomFactor, dataTypeMax * 0.01);

    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const mouseRel = (e.clientX - rect.left) / rect.width;
    const pivot = windowMin + range * mouseRel;

    windowMin = Math.max(0, Math.round(pivot - newRange * mouseRel));
    windowMax = Math.min(dataTypeMax, Math.round(pivot + newRange * (1 - mouseRel)));
  }

  useEventListener(() => histContainerEl, 'wheel', onHistWheel, { passive: false });

  // ── Handlers: Auto Fit & Auto Levels ──────────────────────────────

  function autoFit() {
    if (!hasValidData || !histData) return;
    let lo = 0;
    let hi = numBins - 1;
    for (let i = 0; i < numBins; i++) {
      if (histData[i] > 0) {
        lo = i;
        break;
      }
    }
    for (let i = numBins - 1; i >= 0; i--) {
      if (histData[i] > 0) {
        hi = i;
        break;
      }
    }
    const pad = (hi - lo) * 0.15;
    windowMin = Math.round((Math.max(0, lo - pad) / (numBins - 1)) * dataTypeMax);
    windowMax = Math.round((Math.min(numBins - 1, hi + pad) / (numBins - 1)) * dataTypeMax);
    hasAutoFit = true;
  }

  function autoLevels() {
    if (!hasValidData || !histData) return;
    const result = computeAutoLevels(histData);
    if (result) onLevelsChange(result.min, result.max);
  }

  // ── Handlers: Input Commits ───────────────────────────────────────

  function commitFloatingInput(e: Event, handle: 'min' | 'max') {
    const val = parseInt((e.target as HTMLInputElement).value);
    if (isNaN(val)) return;
    if (handle === 'min') {
      onLevelsChange(Math.max(0, Math.min(val, maxIntensity - 1)) / dataTypeMax, levelsMax);
    } else {
      onLevelsChange(levelsMin, Math.min(dataTypeMax, Math.max(val, minIntensity + 1)) / dataTypeMax);
    }
  }

  function commitWindowInput(e: Event, bound: 'min' | 'max') {
    const val = parseInt((e.target as HTMLInputElement).value);
    if (isNaN(val)) return;
    if (bound === 'min') {
      windowMin = Math.max(0, Math.min(val, windowMax - 1));
    } else {
      windowMax = Math.min(dataTypeMax, Math.max(val, windowMin + 1));
    }
  }

  // ── Effects ───────────────────────────────────────────────────────

  $effect.pre(() => {
    windowMin = 0;
    windowMax = dataTypeMax;
    hasAutoFit = false;
  });

  $effect(() => {
    if (hasValidData && !hasAutoFit) autoFit();
  });
</script>

{#snippet handle(x: number, color: string, ariaLabel: string, value: number, kind: 'min' | 'max')}
  <line
    x1={x}
    y1="0"
    x2={x}
    y2={svgHeight}
    stroke={color}
    stroke-width="1"
    stroke-opacity="0.9"
    pointer-events="none"
  />
  <line
    x1={x}
    y1="0"
    x2={x}
    y2={svgHeight}
    stroke="transparent"
    stroke-width="12"
    class="cursor-ew-resize"
    onpointerdown={(e) => onHandleDown(e, kind)}
    onpointermove={onHandleMove}
    onpointerup={onHandleUp}
    role="slider"
    tabindex="0"
    aria-label={ariaLabel}
    aria-valuenow={value}
  />
{/snippet}

{#snippet floatingLabel(left: number, value: number, kind: 'min' | 'max')}
  <input
    type="text"
    class="hist-input floating-input"
    style:left="{left}px"
    {value}
    onchange={(e) => commitFloatingInput(e, kind)}
  />
{/snippet}

{#snippet histSvg()}
  {#if hasValidData}
    <svg
      width="100%"
      height={svgHeight}
      role="img"
      aria-label="Histogram for {label}"
      class="bg-canvas"
      bind:clientWidth={svgWidth}
    >
      <defs>
        <linearGradient id={gradientId} x1="0%" y1="0%" x2="100%" y2="0%">
          {#each colors as stop, i (i)}
            <stop offset="{colors.length === 1 ? 100 : (i / (colors.length - 1)) * 100}%" stop-color={stop} />
          {/each}
        </linearGradient>
      </defs>

      {#if bgPoints}
        <polyline points={bgPoints} fill="none" stroke="#3f3f46" stroke-width="1" class="non-scaling" />
      {/if}
      {#if fgPolygon}
        <polygon points={fgPolygon} fill="url(#{gradientId})" fill-opacity="0.15" stroke="none" />
      {/if}
      {#if fgPoints}
        <polyline points={fgPoints} fill="none" stroke="url(#{gradientId})" stroke-width="1.5" class="non-scaling" />
      {/if}

      {@render handle(minHandleX, '#10b981', 'Minimum level', minIntensity, 'min')}
      {@render handle(maxHandleX, '#f59e0b', 'Maximum level', maxIntensity, 'max')}

      <rect x="0" y="0" width={minHandleX} height={svgHeight} fill="black" opacity="0.4" pointer-events="none" />
      <rect
        x={maxHandleX}
        y="0"
        width={svgWidth - maxHandleX}
        height={svgHeight}
        fill="var(--surface)"
        opacity="0.4"
        pointer-events="none"
      />
    </svg>
  {:else}
    <div class="flex items-center justify-center" style:height="{svgHeight}px">
      <span class="text-xs text-fg-muted">No histogram data</span>
    </div>
  {/if}
{/snippet}

<div class="relative flex flex-col" bind:clientWidth={columnWidth} style:--label-width="{labelWidth}px">
  {#if visible === false && onVisibilityChange}
    <div class="absolute inset-0 z-10 flex items-center justify-center bg-backdrop">
      <button
        class="flex items-center justify-center rounded p-1 text-fg-muted transition-colors hover:text-fg"
        onclick={() => onVisibilityChange?.(true)}
        aria-label="Show channel"
      >
        <EyeOff width="14" height="14" />
      </button>
    </div>
  {/if}

  <div class="floating-row relative" class:invisible={!hasValidData}>
    {@render floatingLabel(labelPositions.minLeft, minIntensity, 'min')}
    {@render floatingLabel(labelPositions.maxLeft, maxIntensity, 'max')}
  </div>

  <ContextMenu.Root>
    <ContextMenu.Trigger
      class="relative border-b border-b-input bg-transparent"
      bind:ref={histContainerEl}
      ondblclick={autoLevels}
    >
      {@render histSvg()}
    </ContextMenu.Trigger>
    <ContextMenu.Content class="min-w-36" side="top" align="start">
      <ContextMenu.Item onSelect={autoLevels} disabled={!hasValidData}>Auto Levels</ContextMenu.Item>
      <ContextMenu.Item onSelect={autoFit} disabled={!hasValidData}>Auto Fit</ContextMenu.Item>
      <ContextMenu.Separator />
      <ContextMenu.Item
        onSelect={() => {
          windowMin = 0;
          windowMax = dataTypeMax;
        }}
      >
        Reset Window
      </ContextMenu.Item>
      {#if onVisibilityChange}
        <ContextMenu.Separator />
        <ContextMenu.Item onSelect={() => onVisibilityChange?.(!visible)}>
          {visible ? 'Hide' : 'Show'} Channel
        </ContextMenu.Item>
      {/if}
    </ContextMenu.Content>
  </ContextMenu.Root>

  <div class="flex -translate-y-px items-center justify-between">
    <input type="text" class="hist-input" value={windowMin} onchange={(e) => commitWindowInput(e, 'min')} />

    <div class="flex items-center gap-1">
      <ColormapPicker
        {label}
        {colormap}
        {catalog}
        {onColormapChange}
        width={columnWidth}
        align="center"
        triggerClass="cursor-pointer text-xs leading-none font-medium transition-colors hover:brightness-125"
      />
    </div>

    <input
      type="text"
      class="hist-input hist-input-right"
      value={windowMax}
      onchange={(e) => commitWindowInput(e, 'max')}
    />
  </div>
</div>

<style>
  .non-scaling {
    vector-effect: non-scaling-stroke;
  }

  .floating-row {
    height: 14px;
    overflow: visible;
  }

  .hist-input {
    --char-offset: 3px;
    width: var(--label-width, 36px);
    margin-left: calc(-1 * var(--char-offset));
    font-family: var(--font-mono, ui-monospace, monospace);
    font-size: 0.6rem;
    line-height: 1;
    color: var(--color-fg-muted);
    background: transparent;
    border: 1px solid transparent;
    border-radius: 2px;
    outline: none;
    padding: 0;
    user-select: none;
    transition: border-color 0.15s ease;
  }

  .hist-input-right {
    margin-left: 0;
    margin-right: calc(-1 * var(--char-offset));
    text-align: right;
  }

  .hist-input:hover {
    border-color: var(--color-input);
  }

  .hist-input:focus {
    color: var(--color-foreground);
    border-color: var(--color-ring);
  }

  .floating-input {
    position: absolute;
    bottom: 0;
  }
</style>
