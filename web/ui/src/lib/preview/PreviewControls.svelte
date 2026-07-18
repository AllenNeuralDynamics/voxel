<script lang="ts">
  import { Alert, ChevronDown } from '$lib/icons';
  import { type Preview } from '$lib/model';
  import { cn } from '$lib/utils';

  import Histogram from './Histogram.svelte';

  interface Props {
    previewer: Preview;
  }

  let { previewer }: Props = $props();

  let expanded = $state(false);

  const namedChannels = $derived(previewer.channels.filter((c) => c.name));

  const sizedChannels = $derived(namedChannels.filter((c) => c.latestFrameInfo));
  const frameInfo = $derived(sizedChannels[0]?.latestFrameInfo ?? null);
  const sizeMismatch = $derived.by(() => {
    const first = sizedChannels[0]?.latestFrameInfo;
    if (!first || sizedChannels.length <= 1) return false;
    return sizedChannels.some((c) => {
      const fi = c.latestFrameInfo;
      return (
        !fi ||
        fi.width !== first.width ||
        fi.height !== first.height ||
        fi.full_width !== first.full_width ||
        fi.full_height !== first.full_height
      );
    });
  });

  const maxFrameIdx = $derived(Math.max(0, ...sizedChannels.map((c) => c.latestFrameInfo?.frame_idx ?? 0)));
  const overlayCard = 'border border-border bg-surface/80 shadow-xl backdrop-blur-sm rounded-md';
</script>

<div class={cn(overlayCard, 'pointer-events-auto flex w-64 flex-col items-start gap-1.5')}>
  {#if expanded}
    <div class="flex w-64 flex-col divide-y divide-border overflow-hidden px-2.5">
      {#if frameInfo}
        <div class="space-y-1 py-2 text-xs">
          {#if sizeMismatch}
            <div class="flex items-center gap-1.5 text-warning">
              <Alert width="12" height="12" />
              <span class="font-medium">Frame size mismatch</span>
            </div>
            {#each sizedChannels as channel (channel.idx)}
              {@const fi = channel.latestFrameInfo}
              {#if fi}
                <div class="flex justify-between gap-2">
                  <span class="text-fg-muted">{channel.label ?? channel.name}</span>
                  <span class="text-right tabular-nums">{fi.width}×{fi.height} · {fi.full_width}×{fi.full_height}</span>
                </div>
              {/if}
            {/each}
          {:else}
            <div class="flex justify-between gap-2">
              <span class="text-fg-muted">Preview</span>
              <span class="text-right tabular-nums">{frameInfo.width} × {frameInfo.height}</span>
            </div>
            <div class="flex justify-between gap-2">
              <span class="text-fg-muted">Full</span>
              <span class="text-right tabular-nums">{frameInfo.full_width} × {frameInfo.full_height}</span>
            </div>
          {/if}
        </div>
      {/if}
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

  <button
    onclick={() => (expanded = !expanded)}
    class="flex h-7 w-full cursor-pointer items-center justify-between gap-1.5 border border-border/50 bg-floating/90 px-2 font-mono text-xs text-fg-muted shadow-lg backdrop-blur-sm transition-colors hover:bg-element-hover hover:text-fg"
    aria-label={expanded ? 'Hide histograms' : 'Show histograms'}
    title={expanded ? 'Hide histograms' : 'Show histograms'}
  >
    {#if frameInfo}
      <span>Frame <span class="text-fg">{maxFrameIdx}</span></span>
    {:else}
      <span>No frames</span>
    {/if}
    {#if sizeMismatch}
      <Alert width="12" height="12" class="text-warning" />
    {/if}
    <ChevronDown width="14" height="14" class="transition-transform {expanded ? '' : 'rotate-180'}" />
  </button>
</div>
