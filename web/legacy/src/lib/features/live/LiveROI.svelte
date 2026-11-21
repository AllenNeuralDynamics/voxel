<script lang="ts">
  import type { CameraHandle, Instrument } from '$lib/core/model';
  import { deviceLocked } from '$lib/core/model';
  import DivergenceDot from '$lib/features/imaging/DivergenceDot.svelte';
  import LinkToggle from '$lib/features/imaging/LinkToggle.svelte';
  import { Button, CollapsibleSection, SpinBox } from '@voxel/kit';
  import { reportFailure } from '@voxel/kit/failures';
  import { displayName } from '@voxel/kit/format';

  /** The Sensor ROI card of the live controls. It shows nothing when no camera of the active channels has an ROI. */
  let { instrument }: { instrument: Instrument } = $props();

  // The sensor ROI editors: 1 for the cameras that share a linked ROI, and 1 for each other camera.
  const roiEditors = $derived.by(() => {
    const cameras = [
      ...new Map(instrument.activeChannels.map((channel) => [channel.camera.id, channel.camera])).values()
    ];
    const withRoi = cameras.filter((camera) => camera.roi.value && camera.sensorSizePx);
    const link = instrument.links.candidates.find((candidate) => candidate.name === 'roi');
    const linked = new Set(
      link && instrument.links.isLinked(link.key) ? link.members.map((member) => member.device.id) : []
    );
    const shared = withRoi.filter((camera) => linked.has(camera.id));
    return [
      ...(shared.length ? [{ key: 'linked', cameras: shared }] : []),
      ...withRoi.filter((camera) => !linked.has(camera.id)).map((camera) => ({ key: camera.id, cameras: [camera] }))
    ];
  });
</script>

<!-- After the Sensor ROI row of the channel page. A linked ROI moves on all its cameras, so 1 editor covers them. -->
{#snippet roiEditor(cameras: CameraHandle[])}
  {@const camera = cameras[0]}
  {@const roi = camera.roi.value}
  {@const grid = camera.roi.grid}
  {@const sensor = camera.sensorSizePx}
  {@const disabled = deviceLocked(camera, instrument)}
  {@const changed = cameras.some((item) => instrument.divergence.get(item.id)?.roiChanged)}
  <!-- A profile with no ROI uses the full sensor. A patch reaches every linked camera, as the editor's edits do. -->
  {@const savedRoi = instrument.activeProfile?.rois[camera.id]}
  {@const savedText = savedRoi ? `${savedRoi.w} × ${savedRoi.h} at ${savedRoi.x}, ${savedRoi.y}` : 'the full sensor'}
  {#if roi && sensor}
    {@const strokeWidth = Math.max(sensor.x, sensor.y) * 0.004}
    <div class="flex min-w-0 flex-col gap-2">
      <!-- The link toggle and the changed dot on the left, the camera names on the right. -->
      <div class="flex min-w-0 items-center gap-1.5 text-sm text-fg-muted">
        <LinkToggle {instrument} deviceId={camera.id} property="roi" />
        <DivergenceDot
          {changed}
          {disabled}
          title={`Saved: ${savedText}. Click to put it back.`}
          label={`Sensor ROI differs from the saved profile. Put back ${savedText}.`}
          onRevert={() => reportFailure(savedRoi ? camera.roi.patch(savedRoi) : camera.roi.reset())}
        />
        <span class="min-w-0 flex-1 truncate text-right">{cameras.map((item) => displayName(item.id)).join(', ')}</span>
      </div>
      <div class="grid grid-cols-[10rem_minmax(0,1fr)] gap-4">
        <svg
          viewBox="0 0 {sensor.x} {sensor.y}"
          class="w-full self-center"
          style="aspect-ratio: {sensor.x} / {sensor.y};"
          role="img"
          aria-label={`ROI ${roi.w} × ${roi.h} at ${roi.x}, ${roi.y} on a ${sensor.x} × ${sensor.y} sensor`}
        >
          <rect
            x="0"
            y="0"
            width={sensor.x}
            height={sensor.y}
            class="fill-element-bg stroke-line"
            stroke-width={strokeWidth}
          />
          <rect
            x={roi.x}
            y={roi.y}
            width={roi.w}
            height={roi.h}
            class="fill-accent-tint stroke-accent-fg"
            stroke-width={strokeWidth}
          />
        </svg>
        <div class="flex min-w-0 flex-col justify-between gap-2">
          <div class="grid grid-cols-2 gap-2">
            <SpinBox
              {disabled}
              value={roi.x}
              onChange={(value) => camera.roi.patchDim({ x: value })}
              min={0}
              max={(grid?.h.max ?? 0) - roi.w}
              step={grid?.h.step ?? 1}
              prefix="x"
              size="sm"
            />
            <SpinBox
              {disabled}
              value={roi.y}
              onChange={(value) => camera.roi.patchDim({ y: value })}
              min={0}
              max={(grid?.v.max ?? 0) - roi.h}
              step={grid?.v.step ?? 1}
              prefix="y"
              size="sm"
            />
            <SpinBox
              {disabled}
              value={roi.w}
              onChange={(value) => camera.roi.patchDim({ w: value })}
              min={grid?.h.min ?? 1}
              max={grid?.h.max ?? 99999}
              step={grid?.h.step ?? 1}
              prefix="w"
              size="sm"
            />
            <SpinBox
              {disabled}
              value={roi.h}
              onChange={(value) => camera.roi.patchDim({ h: value })}
              min={grid?.v.min ?? 1}
              max={grid?.v.max ?? 99999}
              step={grid?.v.step ?? 1}
              prefix="h"
              size="sm"
            />
          </div>
          <div class="grid grid-cols-2 gap-2">
            <Button variant="secondary" {disabled} onclick={() => reportFailure(camera.roi.center())}>Center</Button>
            <Button variant="secondary" {disabled} onclick={() => reportFailure(camera.roi.reset())}>Reset</Button>
          </div>
        </div>
      </div>
    </div>
  {/if}
{/snippet}

{#if roiEditors.length}
  <CollapsibleSection heading="Sensor ROI">
    <div class="flex flex-col gap-4">
      {#each roiEditors as editor (editor.key)}
        {@render roiEditor(editor.cameras)}
      {/each}
    </div>
  </CollapsibleSection>
{/if}
