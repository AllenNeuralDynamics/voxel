<script lang="ts">
  import {
    getChannelFor,
    isPropDiverged,
    type Session,
    type Camera,
    type ROIGrid,
    type DeliminatedValue,
    type EnumeratedValue
  } from '$lib/app';
  import { Link, LinkOff, Restore, ChevronDown, ChevronRight } from '$lib/icons';
  import { Button, Select, SpinBox } from '$lib/kit';
  import { SvelteSet } from 'svelte/reactivity';
  import { watch } from 'runed';
  import { cn } from '$lib/utils';
  // import { Slider } from '$lib/kit';

  interface Props {
    session: Session;
    class?: string;
  }

  let { session, class: className }: Props = $props();

  let roiExpanded = $state(true);

  // ── Camera lists ──

  const profileCameraIds = $derived.by(() => {
    const ids = new SvelteSet<string>();
    for (const ch of Object.values(session.profiles.activeChannels)) {
      if (ch.detection) ids.add(ch.detection);
    }
    return ids;
  });
  const cameras = $derived(Object.values(session.cameras).filter((c) => profileCameraIds.has(c.deviceId)));
  const otherCameras = $derived(Object.values(session.cameras).filter((c) => !profileCameraIds.has(c.deviceId)));

  // ── Linking state ──

  let linkedIds = new SvelteSet<string>();

  watch(
    () => session.profiles.activeId,
    () => {
      linkedIds.clear();
      for (const c of cameras) linkedIds.add(c.deviceId);
    }
  );

  function toggleLink(deviceId: string) {
    if (linkedIds.has(deviceId)) linkedIds.delete(deviceId);
    else linkedIds.add(deviceId);
  }

  const linkedCameras = $derived(cameras.filter((c) => linkedIds.has(c.deviceId)));

  // ── Merged constraints for linked cameras ──

  interface Bounds {
    min: number;
    max: number;
    step: number;
  }

  interface CardConstraints {
    exposure: Bounds;
    frameRate: Bounds;
    binningOptions: number[];
    pixelFormatOptions: string[];
    roiGrid: ROIGrid | undefined;
  }

  function delimBounds(d: DeliminatedValue | undefined, fallback: Bounds): Bounds {
    return { min: d?.min ?? fallback.min, max: d?.max ?? fallback.max, step: d?.step ?? fallback.step };
  }

  const EXPOSURE_FALLBACK: Bounds = { min: 0, max: 1000, step: 0.1 };
  const FRAME_RATE_FALLBACK: Bounds = { min: 0, max: 100, step: 0.1 };

  function mergeBounds(cameras: Camera[], get: (c: Camera) => DeliminatedValue | undefined, fallback: Bounds): Bounds {
    let min = -Infinity,
      max = Infinity,
      step = 0;
    for (const c of cameras) {
      const d = get(c);
      min = Math.max(min, d?.min ?? fallback.min);
      max = Math.min(max, d?.max ?? fallback.max);
      step = Math.max(step, d?.step ?? fallback.step);
    }
    return {
      min: min === -Infinity ? fallback.min : min,
      max: max === Infinity ? fallback.max : max,
      step: step || fallback.step
    };
  }

  function intersectOptions<T>(cameras: Camera[], get: (c: Camera) => EnumeratedValue | undefined): T[] {
    const sets = cameras.map((c) => new Set(get(c)?.options ?? []));
    if (sets.length === 0) return [];
    let common = sets[0];
    for (let i = 1; i < sets.length; i++) {
      common = new Set([...common].filter((v) => sets[i].has(v)));
    }
    return [...common] as T[];
  }

  const mergedConstraints = $derived.by<CardConstraints>(() => {
    const cams = linkedCameras;
    if (cams.length === 0)
      return {
        exposure: EXPOSURE_FALLBACK,
        frameRate: FRAME_RATE_FALLBACK,
        binningOptions: [],
        pixelFormatOptions: [],
        roiGrid: undefined
      };

    const grids = cams.map((c) => c.roiGrid).filter((g): g is ROIGrid => !!g);
    const roiGrid: ROIGrid | undefined =
      grids.length > 0
        ? {
            h: {
              min: Math.max(...grids.map((g) => g.h.min)),
              max: Math.min(...grids.map((g) => g.h.max)),
              step: Math.max(...grids.map((g) => g.h.step))
            },
            v: {
              min: Math.max(...grids.map((g) => g.v.min)),
              max: Math.min(...grids.map((g) => g.v.max)),
              step: Math.max(...grids.map((g) => g.v.step))
            }
          }
        : undefined;

    return {
      exposure: mergeBounds(cams, (c) => c.exposure, EXPOSURE_FALLBACK),
      frameRate: mergeBounds(cams, (c) => c.frameRate, FRAME_RATE_FALLBACK),
      binningOptions: intersectOptions<number>(cams, (c) => c.binning).sort((a, b) => a - b),
      pixelFormatOptions: intersectOptions<string>(cams, (c) => c.pixelFormat).sort(),
      roiGrid
    };
  });

  function getConstraints(camera: Camera): CardConstraints {
    if (linkedIds.has(camera.deviceId) && linkedCameras.length > 1) {
      return mergedConstraints;
    }
    return {
      exposure: delimBounds(camera.exposure, EXPOSURE_FALLBACK),
      frameRate: delimBounds(camera.frameRate, FRAME_RATE_FALLBACK),
      binningOptions: camera.binning?.options?.filter((o): o is number => typeof o === 'number') ?? [],
      pixelFormatOptions: camera.pixelFormat?.options?.filter((o): o is string => typeof o === 'string') ?? [],
      roiGrid: camera.roiGrid
    };
  }

  // ── Linked action helpers ──

  function forLinked(source: Camera, fn: (c: Camera) => void) {
    if (linkedIds.has(source.deviceId) && linkedCameras.length > 1) {
      for (const cam of linkedCameras) fn(cam);
    } else {
      fn(source);
    }
  }

  function forLinkedAsync(source: Camera, fn: (id: string) => Promise<void> | void) {
    if (linkedIds.has(source.deviceId) && linkedCameras.length > 1) {
      for (const cam of linkedCameras) fn(cam.deviceId);
    } else {
      fn(source.deviceId);
    }
  }

  // ── Helpers ──

  function modeDotColor(mode: string | undefined): string {
    if (mode === 'PREVIEW') return 'bg-success';
    if (mode === 'ACQUISITION') return 'bg-warning';
    return 'bg-fg-muted/40';
  }

  function modeLabel(mode: string | undefined): string {
    if (mode === 'PREVIEW') return 'Preview';
    if (mode === 'ACQUISITION') return 'Acquiring';
    return 'Idle';
  }

  function formatSaved(value: unknown, decimals: number): string {
    return typeof value === 'number' ? value.toFixed(decimals) : String(value ?? '');
  }

  function exposureDecimals(step: number): number {
    if (step >= 1) return 0;
    if (step >= 0.1) return 1;
    if (step >= 0.01) return 2;
    return 3;
  }
</script>

{#snippet unsavedDot(saved: unknown, isDisabled: boolean)}
  {#if !isDisabled && (saved === undefined || saved === null)}
    <span class="inline-block size-1 rounded-full bg-warning opacity-70"></span>
  {/if}
{/snippet}

{#snippet cameraCard(camera: Camera, isOther: boolean)}
  {@const isLinked = linkedIds.has(camera.deviceId)}
  {@const constraints = isOther
    ? {
        exposure: delimBounds(camera.exposure, EXPOSURE_FALLBACK),
        frameRate: delimBounds(camera.frameRate, FRAME_RATE_FALLBACK),
        binningOptions: camera.binning?.options?.filter((o): o is number => typeof o === 'number') ?? [],
        pixelFormatOptions: camera.pixelFormat?.options?.filter((o): o is string => typeof o === 'string') ?? [],
        roiGrid: camera.roiGrid
      }
    : getConstraints(camera)}
  {@const activeProfileId = session.profiles.activeId}
  {@const channelLabel =
    !isOther && activeProfileId
      ? (getChannelFor(session.rig_cfg, activeProfileId, camera.deviceId)?.config?.label ??
        getChannelFor(session.rig_cfg, activeProfileId, camera.deviceId)?.id)
      : undefined}
  {@const savedProps = isOther ? undefined : session.profiles.savedProps(camera.deviceId)}
  {@const savedRoi = isOther ? undefined : session.profiles.savedRoi(camera.deviceId)}
  {@const expDiverged = isPropDiverged(savedProps?.exposure_time_ms, camera.exposure?.value)}
  {@const frDiverged = isPropDiverged(savedProps?.frame_rate_hz, camera.frameRate?.value)}
  {@const binDiverged = isPropDiverged(savedProps?.binning, camera.binning?.value)}
  {@const fmtDiverged = isPropDiverged(savedProps?.pixel_format, camera.pixelFormat?.value)}
  {@const anyPropDiverged = expDiverged || frDiverged || binDiverged || fmtDiverged}
  {@const anyRoiDiverged =
    savedRoi != null &&
    camera.roi != null &&
    (savedRoi.x !== camera.roi.x ||
      savedRoi.y !== camera.roi.y ||
      savedRoi.w !== camera.roi.w ||
      savedRoi.h !== camera.roi.h)}
  {@const anyDiverged = anyPropDiverged || anyRoiDiverged}
  {@const hasUnsaved = !savedProps || !savedRoi}
  {@const sensorW = camera.sensorSizePx?.x ?? 1}
  {@const sensorH = camera.sensorSizePx?.y ?? 1}
  {@const strokeWidth = Math.max(sensorW, sensorH) * 0.004}
  {@const frameSizePx = camera.frameSizePx}
  {@const frameSizeMb = camera.frameSizeMb}

  <div class={cn('flex flex-col rounded border border-border bg-surface px-3', isOther && 'opacity-60')}>
    <!-- ═══ Header ═══ -->
    <div class="flex h-ui-md items-center gap-2">
      <span class="text-sm font-medium">{camera.deviceId}</span>
      {#if channelLabel}
        <span class="rounded-full bg-element-bg px-1.5 py-px text-xs text-fg-muted">{channelLabel}</span>
      {/if}
      {#if isOther}
        <span class="ml-auto rounded-full bg-fg-muted/10 px-1.5 py-px text-xs text-fg-muted">Not in profile</span>
      {:else}
        <div class="ml-auto flex items-center gap-1.5">
          {#if anyDiverged || hasUnsaved}
            {#if anyDiverged}
              <Button
                variant="ghost"
                size="icon-xs"
                onclick={() => {
                  if (anyPropDiverged) forLinkedAsync(camera, (id) => session.profiles.applyProps([id]));
                  if (anyRoiDiverged) forLinkedAsync(camera, (id) => session.profiles.applyRoi(id));
                }}
                title="Revert to saved"
              >
                <Restore width="14" height="14" />
              </Button>
            {/if}
            <Button
              variant="ghost"
              size="xs"
              class="text-warning/80"
              onclick={() => {
                forLinkedAsync(camera, (id) => session.profiles.saveProps(id));
                forLinkedAsync(camera, (id) => session.profiles.saveRoi(id));
              }}
            >
              Save
            </Button>
          {/if}
          {#if cameras.length > 1}
            <button
              class={cn(
                'flex items-center gap-1 rounded px-1.5 py-0.5 text-xs transition-colors',
                isLinked ? 'bg-primary/15 text-primary' : 'text-fg-muted hover:text-fg'
              )}
              onclick={() => toggleLink(camera.deviceId)}
              title={isLinked ? 'Unlink camera' : 'Link camera'}
            >
              {#if isLinked}
                <Link width="14" height="14" />
                <span>Linked</span>
              {:else}
                <LinkOff width="14" height="14" />
              {/if}
            </button>
          {/if}
        </div>
      {/if}
    </div>

    <hr class="-mx-3 mb-2 border-border" />

    <!-- ═══ Properties Section ═══ -->
    <div class="flex flex-col gap-3 pb-1">
      <!-- Exposure (old layout, commented out for potential reuse)
      <div class="flex flex-col gap-1">
        <div class="flex items-start justify-between">
          <div class="flex h-ui-xs items-center gap-1">
            <span class="text-xs text-fg-muted">Exposure</span>
            {@render unsavedDot(savedProps?.exposure_time_ms, isOther)}
            {#if expDiverged}
              <span class="text-xs text-warning/70">· {formatSaved(savedProps?.exposure_time_ms, exposureDecimals(constraints.exposure.step))} ms</span>
            {/if}
          </div>
          <SpinBox
            value={camera.exposure?.value ?? 0}
            min={constraints.exposure.min}
            max={constraints.exposure.max}
            step={constraints.exposure.step}
            decimals={exposureDecimals(constraints.exposure.step)}
            suffix="ms"
            numCharacters={7}
            variant="ghost"
            appearance="full"
            align="left"
            size="xs"
            onChange={(v) => forLinked(camera, (c) => c.setExposure(v))}
          />
        </div>
        <Slider
          target={camera.exposure?.value ?? 0}
          min={constraints.exposure.min}
          max={constraints.exposure.max}
          step={constraints.exposure.step}
          onChange={(v) => forLinked(camera, (c) => c.setExposure(v))}
        />
      </div>
      -->

      <div class="grid grid-cols-[repeat(auto-fit,minmax(22rem,1fr))] gap-x-3 gap-y-2">
        <div class="flex flex-wrap gap-x-3 gap-y-2 *:min-w-40 *:flex-1">
          <div class="flex flex-col gap-1">
            <div class="flex items-center gap-1">
              <span class="text-xs text-fg-muted">Exposure</span>
              {@render unsavedDot(savedProps?.exposure_time_ms, isOther)}
              {#if expDiverged}
                <span class="text-xs text-warning/70"
                  >· {formatSaved(savedProps?.exposure_time_ms, exposureDecimals(constraints.exposure.step))} ms</span
                >
              {/if}
            </div>
            <SpinBox
              value={camera.exposure?.value ?? 0}
              min={constraints.exposure.min}
              max={constraints.exposure.max}
              step={constraints.exposure.step}
              decimals={exposureDecimals(constraints.exposure.step)}
              suffix="ms"
              appearance="full"
              align="left"
              size="xs"
              onChange={(v) => forLinked(camera, (c) => c.setExposure(v))}
            />
          </div>
          <div class="flex flex-col gap-1">
            <div class="flex items-center gap-1">
              <span class="text-xs text-fg-muted">Frame Rate</span>
              {@render unsavedDot(savedProps?.frame_rate_hz, isOther)}
              {#if frDiverged}
                <span class="text-xs text-warning/70">· {formatSaved(savedProps?.frame_rate_hz, 2)} Hz</span>
              {/if}
            </div>
            <SpinBox
              value={camera.frameRate?.value ?? 0}
              min={constraints.frameRate.min}
              max={constraints.frameRate.max}
              step={constraints.frameRate.step}
              decimals={2}
              suffix="Hz"
              appearance="full"
              align="left"
              size="xs"
              onChange={(v) => forLinked(camera, (c) => c.setFrameRate(v))}
            />
          </div>
        </div>
        <div class="flex flex-wrap gap-x-3 gap-y-2 *:min-w-40 *:flex-1">
          <div class="flex flex-col gap-1">
            <div class="flex items-center gap-1">
              <span class="text-xs text-fg-muted">Binning</span>
              {@render unsavedDot(savedProps?.binning, isOther)}
              {#if binDiverged}
                <span class="text-xs text-warning/70">· {savedProps?.binning}x</span>
              {/if}
            </div>
            <Select
              value={String(camera.binning?.value ?? '')}
              options={constraints.binningOptions.length > 0
                ? constraints.binningOptions.map((b) => ({ value: String(b), label: `${b}x` }))
                : camera.binning?.value != null
                  ? [{ value: String(camera.binning.value), label: `${camera.binning.value}x` }]
                  : []}
              size="xs"
              disabled={constraints.binningOptions.length <= 1}
              onchange={(v) => forLinked(camera, (c) => c.setBinning(Number(v)))}
            />
          </div>
          <div class="flex flex-col gap-1">
            <div class="flex items-center gap-1">
              <span class="text-xs text-fg-muted">Format</span>
              {@render unsavedDot(savedProps?.pixel_format, isOther)}
              {#if fmtDiverged}
                <span class="text-xs text-warning/70">· {savedProps?.pixel_format}</span>
              {/if}
            </div>
            <Select
              value={String(camera.pixelFormat?.value ?? '')}
              options={constraints.pixelFormatOptions.length > 0
                ? constraints.pixelFormatOptions.map((f) => ({ value: f, label: f }))
                : camera.pixelFormat?.value != null
                  ? [{ value: String(camera.pixelFormat.value), label: String(camera.pixelFormat.value) }]
                  : []}
              size="xs"
              disabled={constraints.pixelFormatOptions.length <= 1}
              onchange={(v) => forLinked(camera, (c) => c.setPixelFormat(v))}
            />
          </div>
        </div>
      </div>
    </div>

    <!-- ═══ ROI Section ═══ -->
    {#if camera.roi && camera.sensorSizePx}
      <button
        class="-mx-3 my-2 flex cursor-pointer items-center gap-2 px-3 text-fg-muted transition-colors hover:text-fg"
        onclick={() => (roiExpanded = !roiExpanded)}
      >
        <span class="text-xs font-medium tracking-wide uppercase">ROI</span>
        {#if !isOther && !savedRoi}
          {@render unsavedDot(savedRoi, isOther)}
        {:else if anyRoiDiverged}
          <span class="text-xs text-warning/70">*</span>
        {:else}
          <span class="invisible text-xs">*</span>
        {/if}
        <hr class="flex-1 border-border" />
        {#if roiExpanded}
          <ChevronDown width="12" height="12" />
        {:else}
          <ChevronRight width="12" height="12" />
        {/if}
      </button>

      <div class="flex flex-col gap-2">
        {#if roiExpanded}
          <div class="grid grid-cols-[minmax(120px,1fr)_3fr] gap-3">
            <!-- SVG sensor diagram -->
            <svg
              viewBox="0 0 {sensorW} {sensorH}"
              class="w-full self-center"
              style="aspect-ratio: {sensorW} / {sensorH};"
            >
              <rect
                x="0"
                y="0"
                width={sensorW}
                height={sensorH}
                class="fill-fg-faint/10 stroke-border"
                stroke-width={strokeWidth}
              />
              <rect
                x={camera.roi.x}
                y={camera.roi.y}
                width={camera.roi.w}
                height={camera.roi.h}
                class="fill-fg/10 stroke-fg/30"
                stroke-width={strokeWidth}
              />
            </svg>

            <!-- Spinboxes + spatial actions (2×3 grid) -->
            <div class="flex min-w-0 flex-1 flex-col justify-between gap-2">
              <div class="grid grid-cols-2 gap-2">
                <SpinBox
                  value={camera.roi.x}
                  min={0}
                  max={(constraints.roiGrid?.h.max ?? 0) - (camera.roi.w ?? 0)}
                  step={constraints.roiGrid?.h.step ?? 1}
                  prefix="x"
                  numCharacters={7}
                  appearance="full"
                  size="xs"
                  onChange={(v) => forLinked(camera, (c) => c.updateRoi({ ...c.roi!, x: v }))}
                />
                <SpinBox
                  value={camera.roi.y}
                  min={0}
                  max={(constraints.roiGrid?.v.max ?? 0) - (camera.roi.h ?? 0)}
                  step={constraints.roiGrid?.v.step ?? 1}
                  prefix="y"
                  numCharacters={7}
                  appearance="full"
                  size="xs"
                  onChange={(v) => forLinked(camera, (c) => c.updateRoi({ ...c.roi!, y: v }))}
                />
                <SpinBox
                  value={camera.roi.w}
                  min={constraints.roiGrid?.h.min ?? 1}
                  max={constraints.roiGrid?.h.max ?? 99999}
                  step={constraints.roiGrid?.h.step ?? 1}
                  prefix="w"
                  numCharacters={7}
                  appearance="full"
                  size="xs"
                  onChange={(v) => forLinked(camera, (c) => c.updateRoi({ ...c.roi!, w: v }))}
                />
                <SpinBox
                  value={camera.roi.h}
                  min={constraints.roiGrid?.v.min ?? 1}
                  max={constraints.roiGrid?.v.max ?? 99999}
                  step={constraints.roiGrid?.v.step ?? 1}
                  prefix="h"
                  numCharacters={7}
                  appearance="full"
                  size="xs"
                  onChange={(v) => forLinked(camera, (c) => c.updateRoi({ ...c.roi!, h: v }))}
                />
              </div>
              <div class="grid grid-cols-2 gap-2">
                <Button
                  variant="secondary"
                  size="xs"
                  onclick={() =>
                    forLinked(camera, (c) => {
                      const sz = c.sensorSizePx;
                      if (sz)
                        c.updateRoi({
                          ...c.roi!,
                          x: Math.floor((sz.x - (c.roi?.w ?? sz.x)) / 2),
                          y: Math.floor((sz.y - (c.roi?.h ?? sz.y)) / 2)
                        });
                    })}>Center</Button
                >
                <Button
                  variant="secondary"
                  size="xs"
                  onclick={() =>
                    forLinked(camera, (c) => {
                      const sz = c.sensorSizePx;
                      if (sz) c.updateRoi({ x: 0, y: 0, w: sz.x, h: sz.y });
                    })}>Reset</Button
                >
              </div>
            </div>
          </div>
        {/if}
      </div>
    {/if}

    <!-- ═══ Footer ═══ -->
    <hr class="-mx-3 my-2 border-border" />

    <div class="flex items-center justify-between pb-2 font-mono text-xs text-fg-muted tabular-nums">
      <div class="flex items-center gap-1.5">
        <div class="h-2 w-2 rounded-full {modeDotColor(camera.mode)}"></div>
        <span class="text-xs text-fg-muted">{modeLabel(camera.mode)}</span>
      </div>
      {#if camera.streamInfo}
        {@const info = camera.streamInfo}
        <div class="flex items-center">
          <span>{info.frame_rate_fps.toFixed(1)} fps</span>
          <span>&ensp;&middot;&ensp;</span>
          <span>{info.data_rate_mbs.toFixed(1)} MB/s</span>
          {#if info.dropped_frames > 0}
            <span>&ensp;&middot;&ensp;</span>
            <span class="text-danger">{info.dropped_frames} dropped</span>
          {/if}
        </div>
      {:else}
        <div></div>
      {/if}
      <div class="flex items-center">
        {#if frameSizePx}
          <span>{frameSizePx.x}&times;{frameSizePx.y}</span>
          {#if frameSizeMb != null}
            <span>&ensp;&middot;&ensp;{frameSizeMb.toFixed(1)} MB</span>
          {/if}
        {/if}
      </div>
    </div>
  </div>
{/snippet}

{#if !session.profiles.activeId}
  <div class={cn('flex items-center justify-center py-12', className)}>
    <p class="text-sm text-fg-muted">No active profile</p>
  </div>
{:else if cameras.length === 0 && otherCameras.length === 0}
  <div class={cn('flex items-center justify-center py-12', className)}>
    <p class="text-sm text-fg-muted">No cameras configured</p>
  </div>
{:else}
  <div class={cn('grid grid-cols-[repeat(auto-fit,minmax(20rem,1fr))] items-start gap-4', className)}>
    {#each [...cameras, ...otherCameras] as camera (camera.deviceId)}
      {@render cameraCard(camera, !profileCameraIds.has(camera.deviceId))}
    {/each}
  </div>
{/if}
