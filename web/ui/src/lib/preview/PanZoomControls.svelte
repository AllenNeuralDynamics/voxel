<script lang="ts">
  import { Restore } from '$lib/icons';
  import { SpinBox } from '$lib/kit';
  import type { PreviewManager } from '$lib/preview';
  import { isDefaultViewport } from '$lib/preview';
  import { clampTopLeft } from '$lib/utils';

  interface Props {
    previewer: PreviewManager;
  }

  let { previewer }: Props = $props();

  let isDefault = $derived(isDefaultViewport(previewer.viewport));

  // Local state for inputs (synced from previewer)
  let panX = $state(0);
  let panY = $state(0);
  let magnification = $state(1);

  // Sync local state with previewer
  $effect.pre(() => {
    panX = previewer.viewport.x;
    panY = previewer.viewport.y;
    magnification = 1 / previewer.viewport.w;
  });

  function handlePanXChange(value: number) {
    previewer.setViewport({ ...previewer.viewport, x: value });
    previewer.queueViewportUpdate(previewer.viewport);
  }

  function handlePanYChange(value: number) {
    previewer.setViewport({ ...previewer.viewport, y: value });
    previewer.queueViewportUpdate(previewer.viewport);
  }

  function handleZoomChange(value: number) {
    const newW = Math.max(0.01, Math.min(1.0, 1 / value));
    const newH = newW;
    // Zoom toward center of current viewport
    const centerX = previewer.viewport.x + previewer.viewport.w / 2;
    const centerY = previewer.viewport.y + previewer.viewport.h / 2;
    const newX = clampTopLeft(centerX - newW / 2, newW);
    const newY = clampTopLeft(centerY - newH / 2, newH);
    previewer.setViewport({ x: newX, y: newY, w: newW, h: newH });
    previewer.queueViewportUpdate(previewer.viewport);
  }
</script>

<div class="flex items-center gap-1 font-mono text-xs">
  <button
    onclick={() => previewer.resetViewport()}
    disabled={isDefault}
    class="flex cursor-pointer items-center rounded p-1 text-fg transition-colors hover:bg-element-hover disabled:opacity-60"
    aria-label="Reset pan and zoom"
  >
    <Restore width="14" height="14" />
  </button>
  <div class="flex items-center gap-4">
    <SpinBox
      bind:value={magnification}
      min={1}
      max={100}
      step={0.1}
      resetValue={1}
      decimals={1}
      numCharacters={5}
      size="xs"
      variant="filled"
      prefix="Zoom"
      suffix="x"
      onChange={handleZoomChange}
    />
    <SpinBox
      bind:value={panX}
      min={0}
      max={1}
      step={0.01}
      resetValue={0}
      decimals={2}
      numCharacters={5}
      size="xs"
      variant="filled"
      prefix="Pan X"
      onChange={handlePanXChange}
    />
    <SpinBox
      bind:value={panY}
      min={0}
      max={1}
      step={0.01}
      resetValue={0}
      decimals={2}
      numCharacters={5}
      size="xs"
      variant="filled"
      prefix="Pan Y"
      onChange={handlePanYChange}
    />
  </div>
</div>
