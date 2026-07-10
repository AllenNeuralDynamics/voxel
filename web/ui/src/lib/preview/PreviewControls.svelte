<script lang="ts">
  import { ChevronDown } from '$lib/icons';
  import { SpinBox } from '$lib/kit';
  import { type Preview } from '$lib/model';
  import { clampTopLeft } from '$lib/utils';

  import Histogram from './Histogram.svelte';

  interface Props {
    previewer: Preview;
  }

  let { previewer }: Props = $props();

  // Local state for inputs (synced from previewer)
  let panX = $state(0);
  let panY = $state(0);
  let magnification = $state(1);
  let showHistograms = $state(false);

  const namedChannels = $derived(previewer.channels.filter((c) => c.name));
  const hasHistograms = $derived(showHistograms && namedChannels.length > 0);

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

<div
  class="pointer-events-auto flex w-fit flex-col overflow-hidden rounded-xs border border-border/50 bg-floating/90 pb-1.5 shadow-lg backdrop-blur-sm"
>
  {#if hasHistograms}
    <div class="flex w-0 min-w-full flex-col divide-y divide-border px-2.5">
      {#each namedChannels as channel (channel.idx)}
        <div class="py-2">
          <Histogram
            label={channel.label ?? channel.config?.label ?? channel.name ?? ''}
            histData={channel.latestHistogram}
            levelsMin={channel.levelsMin}
            levelsMax={channel.levelsMax}
            onLevelsChange={(min, max) => {
              if (channel.name) previewer.setChannelLevels(channel.name, min, max);
            }}
            colormap={channel.colormap}
            catalog={previewer.catalog}
            onColormapChange={(cmap) => {
              if (channel.name) previewer.setChannelColormap(channel.name, cmap);
            }}
            visible={channel.visible}
            onVisibilityChange={(v) => (channel.visible = v)}
          />
        </div>
      {/each}
    </div>
  {/if}

  <div class="flex items-center gap-2 px-2.5 pt-1.5 font-mono text-xs {hasHistograms ? 'border-t border-border' : ''}">
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
      prefix="X"
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
      prefix="Y"
      onChange={handlePanYChange}
    />
    <button
      onclick={() => (showHistograms = !showHistograms)}
      class="flex cursor-pointer items-center justify-center rounded-full p-1 text-fg-muted transition-colors hover:bg-element-hover hover:text-fg"
      aria-label={showHistograms ? 'Hide histograms' : 'Show histograms'}
      title={showHistograms ? 'Hide histograms' : 'Show histograms'}
    >
      <ChevronDown width="14" height="14" class="transition-transform {showHistograms ? '' : 'rotate-180'}" />
    </button>
  </div>
</div>
