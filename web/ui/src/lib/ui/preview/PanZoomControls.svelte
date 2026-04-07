<script lang="ts">
  import { Restore } from '$lib/icons';
  import { SpinBox } from '$lib/ui/kit';
  import type { PreviewState } from '$lib/main';
  import { isDefaultViewport } from '$lib/main/preview.svelte.ts';
  import { clampTopLeft } from '$lib/utils';

  interface Props {
    previewer: PreviewState;
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
    class="flex items-center rounded p-1 text-fg transition-colors hover:bg-element-hover disabled:cursor-not-allowed disabled:opacity-0"
    aria-label="Reset pan and zoom"
  >
    <Restore width="12" height="12" />
  </button>
  <div class="flex items-center gap-4">
    <SpinBox
      bind:value={magnification}
      min={1}
      max={100}
      step={0.1}
      snapValue={1}
      decimals={1}
      numCharacters={5}
      size="xs"
      prefix="Zoom"
      suffix="x"
      onChange={handleZoomChange}
    />
    <SpinBox
      bind:value={panY}
      min={0}
      max={1}
      step={0.01}
      snapValue={0}
      decimals={2}
      numCharacters={5}
      size="xs"
      prefix="Pan X"
      onChange={handlePanYChange}
    />
    <SpinBox
      bind:value={panX}
      min={0}
      max={1}
      step={0.01}
      snapValue={0}
      decimals={2}
      numCharacters={5}
      size="xs"
      prefix="Pan Y"
      onChange={handlePanXChange}
    />
  </div>
</div>
