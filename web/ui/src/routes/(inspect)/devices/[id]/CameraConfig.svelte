<script lang="ts">
  import type { Microscope } from '$lib/microscope';
  import { cn, sanitizeString } from '$lib/utils';
  import { Select, SpinBox, Button, Slider } from '$lib/kit';
  import DeviceBrowser from '$lib/microscope/device/DeviceBrowser.svelte';

  const cameraExclusions = {
    props: [
      'exposure_time_ms',
      'pixel_format',
      'binning',
      'sensor_size_px',
      'pixel_size_um',
      'pixel_type',
      'frame_size_px',
      'frame_size_mb',
      'frame_area_um',
      'roi',
      'roi_grid',
      'frame_rate_hz',
      'stream_info'
    ],
    cmds: ['update_roi']
  };

  interface Props {
    microscope: Microscope;
    deviceId: string;
  }

  let { microscope, deviceId }: Props = $props();

  const camera = $derived(microscope.cameras.get(deviceId));

  // Sensor details
  const sensorSize = $derived(camera?.sensorSizePx);
  const pixelSize = $derived(camera?.pixelSizeUm);
  const pixelType = $derived(camera?.getProp('pixel_type')?.value);
  const frameAreaUm = $derived(camera?.frameAreaUm);

  // ROI
  const roi = $derived(camera?.roi);
  const roiGrid = $derived(camera?.roiGrid);
  const frameSize = $derived(camera?.frameSizePx);
  const frameSizeMb = $derived(camera?.frameSizeMb?.value);

  // Stream info
  const frameRateHz = $derived(camera?.frameRate?.value);
  const streamInfo = $derived(camera?.streamInfo);

  // SVG dimensions — sensor defines the coordinate space
  const sensorW = $derived(sensorSize?.x ?? 1);
  const sensorH = $derived(sensorSize?.y ?? 1);

  // Local spinbox values — mutable local state synced from backend roi.
  let roiX = $state(0);
  let roiY = $state(0);
  let roiW = $state(0);
  let roiH = $state(0);

  $effect(() => {
    if (roi) {
      roiX = roi.x;
      roiY = roi.y;
      roiW = roi.w;
      roiH = roi.h;
    }
  });

  function updateRoi(patch: Partial<{ x: number; y: number; w: number; h: number }>) {
    if (!roi) return;
    camera?.updateRoi({ ...roi, ...patch });
  }

  function resetRegion() {
    camera?.updateRoi({ x: 0, y: 0, w: sensorW, h: sensorH });
  }

  const strokeWidth = $derived(Math.max(sensorW, sensorH) * 0.004);
</script>

<section class="space-y-5">
  <!-- Header -->
  <div class="flex items-center justify-between">
    <h2 class="text-base font-medium text-fg">{sanitizeString(deviceId)}</h2>
    <span
      class={cn('h-2 w-2 rounded-full', camera?.connected ? 'bg-success' : 'bg-fg-muted/30')}
      title={camera?.connected ? 'Connected' : 'Disconnected'}
    ></span>
  </div>

  {#if camera?.connected}
    <div class="grid gap-6 lg:grid-cols-[3fr_2fr]">
      <!-- LEFT COLUMN: controls, sensor ROI, dynamic rw, commands -->
      <div class="space-y-5">
        <!-- Exposure Time -->
        {#if camera.exposure}
          {@const exposure = camera.exposure}
          {@const info = camera.interface?.properties?.['exposure_time_ms']}
          <div class="grid gap-1">
            <span class="text-xs font-medium text-fg-muted">{info?.label ?? 'Exposure'}</span>
            <div class="grid grid-cols-[8rem_1fr] items-center gap-3">
              <SpinBox
                value={exposure.value ?? 0}
                min={exposure.min ?? 0}
                max={exposure.max ?? 100}
                step={exposure.step ?? 0.1}
                appearance="full"
                size="xs"
                onChange={(v) => exposure.patch(v)}
              />
              <Slider
                target={exposure.value ?? 0}
                min={exposure.min ?? 0}
                max={exposure.max ?? 100}
                step={exposure.step ?? 0.1}
                onChange={(v) => exposure.patch(v)}
              />
            </div>
          </div>
        {/if}

        <!-- Pixel Format and Binning -->
        <div class="grid grid-cols-2 gap-4">
          {#if camera.pixelFormat}
            {@const pf = camera.pixelFormat}
            {@const info = camera.interface?.properties?.['pixel_format']}
            <div class="grid gap-1">
              <span class="text-xs font-medium text-fg-muted">{info?.label ?? 'Pixel Format'}</span>
              <Select
                value={String(pf.value)}
                options={pf.options.map((o) => ({ value: String(o), label: String(o) }))}
                onchange={(v) => pf.patch(v)}
                size="xs"
              />
            </div>
          {/if}

          {#if camera.binning}
            {@const bin = camera.binning}
            {@const info = camera.interface?.properties?.['binning']}
            <div class="grid gap-1">
              <span class="text-xs font-medium text-fg-muted">{info?.label ?? 'Binning'}</span>
              <Select
                value={String(bin.value)}
                options={bin.options.map((o) => ({ value: String(o), label: `${o}x${o}` }))}
                onchange={(v) => bin.patch(Number(v))}
                size="xs"
              />
            </div>
          {/if}
        </div>

        <!-- Sensor ROI -->
        <div class="space-y-3">
          <div class="flex items-baseline justify-between">
            <h4 class="text-xs font-medium tracking-wide text-fg-muted uppercase">Sensor ROI</h4>
            {#if frameSize}
              <span class="font-mono text-sm text-fg-muted">
                {frameSize.x} &times; {frameSize.y} px{#if frameSizeMb != null}
                  &ensp;|&ensp;{frameSizeMb.toFixed(1)} MB{/if}
              </span>
            {/if}
          </div>

          <!-- SVG sensor diagram -->
          {#if sensorSize && roi}
            <svg
              viewBox="0 0 {sensorW} {sensorH}"
              class="w-full rounded border border-border bg-element-bg"
              style="max-height: 280px;"
              preserveAspectRatio="xMidYMid meet"
            >
              <rect
                x={strokeWidth / 2}
                y={strokeWidth / 2}
                width={sensorW - strokeWidth}
                height={sensorH - strokeWidth}
                class="fill-none stroke-border"
                stroke-width={strokeWidth}
              />
              <rect x="0" y="0" width={sensorW} height={sensorH} class="fill-element-bg" />
              <rect
                x={roi.x}
                y={roi.y}
                width={roi.w}
                height={roi.h}
                class="fill-primary/15 stroke-primary"
                stroke-width={strokeWidth}
              />
            </svg>
          {:else}
            <div class="flex aspect-4/3 items-center justify-center rounded border border-border bg-element-bg">
              <span class="text-sm text-fg-muted">No region data</span>
            </div>
          {/if}

          <!-- ROI spinbox inputs -->
          {#if roi && roiGrid}
            <div class="grid grid-cols-4 gap-2">
              <SpinBox
                value={roiX}
                prefix="x"
                min={0}
                max={roiGrid.h.max - roiW}
                step={roiGrid.h.step}
                onChange={(v) => updateRoi({ x: v })}
                appearance="bordered"
                size="xs"
              />
              <SpinBox
                value={roiY}
                prefix="y"
                min={0}
                max={roiGrid.v.max - roiH}
                step={roiGrid.v.step}
                onChange={(v) => updateRoi({ y: v })}
                appearance="bordered"
                size="xs"
              />
              <SpinBox
                value={roiW}
                prefix="w"
                min={roiGrid.h.min}
                max={roiGrid.h.max}
                step={roiGrid.h.step}
                onChange={(v) => updateRoi({ w: v })}
                appearance="bordered"
                size="xs"
              />
              <SpinBox
                value={roiH}
                prefix="h"
                min={roiGrid.v.min}
                max={roiGrid.v.max}
                step={roiGrid.v.step}
                onChange={(v) => updateRoi({ h: v })}
                appearance="bordered"
                size="xs"
              />
            </div>
            <Button variant="outline" size="sm" onclick={resetRegion} class="w-full">Reset ROI</Button>
          {/if}
        </div>

        <!-- Dynamic: remaining properties + commands -->
        <DeviceBrowser device={camera} exclusions={cameraExclusions} />
      </div>

      <!-- RIGHT COLUMN: sensor info, stream -->
      <div class="space-y-5">
        <!-- Sensor / Pixel size -->
        <div class="grid gap-1 text-sm">
          {#if sensorSize}
            <div class="flex justify-between">
              <span class="text-fg-muted">Sensor</span>
              <span class="font-mono text-fg">{sensorSize.x} &times; {sensorSize.y} px</span>
            </div>
          {/if}
          {#if pixelSize}
            <div class="flex justify-between">
              <span class="text-fg-muted">Pixel</span>
              <span class="font-mono text-fg">{pixelSize.x} &times; {pixelSize.y} &micro;m</span>
            </div>
          {/if}
          {#if pixelType}
            <div class="flex justify-between">
              <span class="text-fg-muted">Type</span>
              <span class="font-mono text-fg">{pixelType}</span>
            </div>
          {/if}
          {#if frameAreaUm}
            <div class="flex justify-between">
              <span class="text-fg-muted">Area</span>
              <span class="font-mono text-fg">
                {(frameAreaUm.x / 1000).toFixed(2)} &times; {(frameAreaUm.y / 1000).toFixed(2)} mm
              </span>
            </div>
          {/if}
        </div>

        <!-- Stream info -->
        <div class="space-y-1">
          <h4 class="text-xs font-medium tracking-wide text-fg-muted uppercase">Stream</h4>
          <div class="grid gap-1 text-sm">
            <div class="flex justify-between">
              <span class="text-fg-muted">Frame Rate</span>
              <span class="font-mono text-fg">
                {typeof frameRateHz === 'number' ? `${frameRateHz.toFixed(1)} fps` : '—'}
              </span>
            </div>
            <div class="flex justify-between">
              <span class="text-fg-muted">Data Rate</span>
              <span class="font-mono text-fg">
                {streamInfo?.data_rate_mbs != null ? `${streamInfo.data_rate_mbs.toFixed(1)} MB/s` : '—'}
              </span>
            </div>
            <div class="flex justify-between">
              <span class="text-fg-muted">Dropped</span>
              <span class={cn('font-mono', streamInfo?.dropped_frames ? 'text-danger' : 'text-fg')}>
                {streamInfo?.dropped_frames != null ? streamInfo.dropped_frames : '—'}
              </span>
            </div>
            <div class="flex justify-between">
              <span class="text-fg-muted">Frame Index</span>
              <span class="font-mono text-fg">
                {streamInfo?.frame_index != null ? streamInfo.frame_index : '—'}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  {:else}
    <div class="flex items-center justify-center py-12">
      <p class="text-base text-fg-muted">Camera not available</p>
    </div>
  {/if}
</section>
