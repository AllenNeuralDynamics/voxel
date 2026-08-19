<script lang="ts">
  import { Button } from '$lib/kit';
  import type { CameraHandle } from '$lib/model';
  import { Enumerated, PropInput } from '$lib/prop';
  import { SpinBox } from '$lib/prop/numeric';
  import { cn } from '$lib/utils';

  import GenericCommands from './GenericCommands.svelte';
  import GenericProperties from './GenericProperties.svelte';

  interface Props {
    camera: CameraHandle;
  }

  const { camera }: Props = $props();
  const propertyCount = $derived(Object.keys(camera.interface?.properties ?? {}).length);
  const customProperties = [
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
  ];
  const customCommands = ['update_roi'];

  const sensorSize = $derived(camera.sensorSizePx);
  const pixelSize = $derived(camera.pixelSizeUm);
  const pixelType = $derived(camera.getProp('pixel_type')?.value);
  const frameAreaUm = $derived(camera.frameAreaUm);
  const roi = $derived(camera.roi.value);
  const roiGrid = $derived(camera.roi.grid);
  const frameSize = $derived(camera.frameSizePx);
  const frameSizeMb = $derived(camera.frameSizeMb?.value);
  const frameRateHz = $derived(camera.frameRate?.value);
  const streamInfo = $derived(camera.streamInfo);
  const sensorWidth = $derived(sensorSize?.x ?? 1);
  const sensorHeight = $derived(sensorSize?.y ?? 1);
  const strokeWidth = $derived(Math.max(sensorWidth, sensorHeight) * 0.004);

  let roiX = $state(0);
  let roiY = $state(0);
  let roiWidth = $state(0);
  let roiHeight = $state(0);

  $effect(() => {
    if (!roi) return;
    roiX = roi.x;
    roiY = roi.y;
    roiWidth = roi.w;
    roiHeight = roi.h;
  });

  function updateRoi(patch: Partial<{ x: number; y: number; w: number; h: number }>): void {
    void camera.roi.patchDim(patch);
  }

  function resetRegion(): void {
    void camera.roi.reset();
  }
</script>

<section>
  <h3 class="mb-3 text-sm font-medium text-fg-muted">Properties</h3>
  {#if propertyCount > 0}
    <div class="space-y-6">
      <div class="flex flex-wrap justify-between gap-8">
        <div class="min-w-82 flex-1 space-y-5">
          {#if camera.exposure}
            {@const info = camera.interface?.properties?.['exposure_time_ms']}
            <div class="grid gap-1">
              <span class="font-medium text-fg-muted">{info?.label ?? 'Exposure'}</span>
              <PropInput model={camera.exposure} size="xs" />
            </div>
          {/if}

          <div class="grid grid-cols-2 gap-4">
            {#if camera.pixelFormat}
              {@const info = camera.interface?.properties?.['pixel_format']}
              <div class="grid gap-1">
                <span class="font-medium text-fg-muted">{info?.label ?? 'Pixel Format'}</span>
                <PropInput model={camera.pixelFormat} size="xs" />
              </div>
            {/if}

            {#if camera.binning}
              {@const info = camera.interface?.properties?.['binning']}
              <div class="grid gap-1">
                <span class="font-medium text-fg-muted">{info?.label ?? 'Binning'}</span>
                <Enumerated.Select model={camera.binning} formatLabel={(option) => `${option}x${option}`} size="xs" />
              </div>
            {/if}
          </div>

          <div class="space-y-3">
            <div class="flex items-baseline justify-between gap-4">
              <h4 class="text-sm font-medium text-fg-muted">Sensor ROI</h4>
              {#if frameSize}
                <span class="font-mono text-fg-muted">
                  {frameSize.x} &times; {frameSize.y} px{#if frameSizeMb != null}
                    &ensp;|&ensp;{frameSizeMb.toFixed(1)} MB{/if}
                </span>
              {/if}
            </div>

            {#if sensorSize && roi}
              <svg
                viewBox="0 0 {sensorWidth} {sensorHeight}"
                class="w-full rounded border border-border bg-element-bg"
                style="max-height: 280px;"
                preserveAspectRatio="xMidYMid meet"
              >
                <rect
                  x={strokeWidth / 2}
                  y={strokeWidth / 2}
                  width={sensorWidth - strokeWidth}
                  height={sensorHeight - strokeWidth}
                  class="fill-none stroke-border"
                  stroke-width={strokeWidth}
                />
                <rect x="0" y="0" width={sensorWidth} height={sensorHeight} class="fill-element-bg" />
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
                <span class="text-fg-muted">No region data</span>
              </div>
            {/if}

            {#if roi && roiGrid}
              <div class="grid grid-cols-4 gap-2">
                <SpinBox
                  model={{
                    value: roiX,
                    onChange: (value) => updateRoi({ x: value }),
                    min: 0,
                    max: roiGrid.h.max - roiWidth,
                    step: roiGrid.h.step
                  }}
                  prefix="x"
                  steppers={false}
                  size="xs"
                />
                <SpinBox
                  model={{
                    value: roiY,
                    onChange: (value) => updateRoi({ y: value }),
                    min: 0,
                    max: roiGrid.v.max - roiHeight,
                    step: roiGrid.v.step
                  }}
                  prefix="y"
                  steppers={false}
                  size="xs"
                />
                <SpinBox
                  model={{
                    value: roiWidth,
                    onChange: (value) => updateRoi({ w: value }),
                    min: roiGrid.h.min,
                    max: roiGrid.h.max,
                    step: roiGrid.h.step
                  }}
                  prefix="w"
                  steppers={false}
                  size="xs"
                />
                <SpinBox
                  model={{
                    value: roiHeight,
                    onChange: (value) => updateRoi({ h: value }),
                    min: roiGrid.v.min,
                    max: roiGrid.v.max,
                    step: roiGrid.v.step
                  }}
                  prefix="h"
                  steppers={false}
                  size="xs"
                />
              </div>
              <Button variant="outline" size="sm" onclick={resetRegion} class="w-full">Reset ROI</Button>
            {/if}
          </div>
        </div>

        <div class="min-w-64 flex-1 space-y-5">
          <div class="grid gap-1 text-fg">
            {#if sensorSize}
              <div class="flex justify-between gap-4">
                <span class="text-fg-muted">Sensor</span>
                <span class="font-mono">{sensorSize.x} &times; {sensorSize.y} px</span>
              </div>
            {/if}
            {#if pixelSize}
              <div class="flex justify-between gap-4">
                <span class="text-fg-muted">Pixel</span>
                <span class="font-mono">{pixelSize.x} &times; {pixelSize.y} &micro;m</span>
              </div>
            {/if}
            {#if pixelType}
              <div class="flex justify-between gap-4">
                <span class="text-fg-muted">Type</span>
                <span class="font-mono">{pixelType}</span>
              </div>
            {/if}
            {#if frameAreaUm}
              <div class="flex justify-between gap-4">
                <span class="text-fg-muted">Area</span>
                <span class="font-mono">
                  {(frameAreaUm.x / 1000).toFixed(2)} &times; {(frameAreaUm.y / 1000).toFixed(2)} mm
                </span>
              </div>
            {/if}
          </div>

          <div class="space-y-1">
            <h4 class="text-sm font-medium text-fg-muted">Stream</h4>
            <div class="grid gap-1 text-fg">
              <div class="flex justify-between gap-4">
                <span class="text-fg-muted">Frame Rate</span>
                <span class="font-mono">
                  {typeof frameRateHz === 'number' ? `${frameRateHz.toFixed(1)} fps` : '—'}
                </span>
              </div>
              <div class="flex justify-between gap-4">
                <span class="text-fg-muted">Data Rate</span>
                <span class="font-mono">
                  {streamInfo?.data_rate_mbs != null ? `${streamInfo.data_rate_mbs.toFixed(1)} MB/s` : '—'}
                </span>
              </div>
              <div class="flex justify-between gap-4">
                <span class="text-fg-muted">Dropped</span>
                <span class={cn('font-mono', streamInfo?.dropped_frames ? 'text-danger' : 'text-fg')}>
                  {streamInfo?.dropped_frames != null ? streamInfo.dropped_frames : '—'}
                </span>
              </div>
              <div class="flex justify-between gap-4">
                <span class="text-fg-muted">Frame Index</span>
                <span class="font-mono">{streamInfo?.frame_index != null ? streamInfo.frame_index : '—'}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <GenericProperties device={camera} exclude={customProperties} />
    </div>
  {:else}
    <p class="text-fg-muted">This device does not expose any live properties.</p>
  {/if}
</section>

<GenericCommands device={camera} exclude={customCommands} />
