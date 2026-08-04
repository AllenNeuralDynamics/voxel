<script lang="ts">
  import { emissionToPreviewColor } from '$lib/colors.svelte';
  import { ChevronDown } from '$lib/icons';

  import Histogram from './Histogram.svelte';
  import type { PreviewSession } from './session.svelte';

  interface Props {
    previewer: PreviewSession;
  }

  let { previewer }: Props = $props();

  let expanded = $state(true);
  const namedChannels = $derived(previewer.channels.filter((channel) => channel.name));
  const visibleChannelCount = $derived(namedChannels.filter((channel) => channel.visible).length);
</script>

<div class="pointer-events-auto flex max-h-full min-h-0 w-68 flex-col overflow-hidden overlay-panel">
  {#if expanded}
    <div class="min-h-0 divide-y divide-border overflow-y-auto border-b border-border px-2.5">
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
            colormapPreference={channel.colormapPreference}
            autoColormap={emissionToPreviewColor(channel.config?.emission)}
            colormap={channel.resolvedColormap}
            catalog={previewer.catalog}
            onColormapChange={(colormap) => {
              if (channel.name) previewer.setChannelColormap(channel.name, colormap);
            }}
            dataTypeMax={2 ** (channel.overviewFrame?.valid_bits ?? 16) - 1}
            visible={channel.visible}
            onVisibilityChange={(visible) => {
              if (channel.name) previewer.setChannelVisible(channel.name, visible);
            }}
          />
        </div>
      {/each}
    </div>
  {/if}

  <button
    type="button"
    onclick={() => (expanded = !expanded)}
    class="flex h-7 w-full shrink-0 cursor-pointer items-center justify-between gap-1.5 px-2 font-mono text-fg-muted transition-colors hover:bg-element-hover hover:text-fg"
    aria-expanded={expanded}
    aria-label={expanded ? 'Hide channel controls' : 'Show channel controls'}
    title={expanded ? 'Hide channel controls' : 'Show channel controls'}
  >
    <span>
      Channels <span class="text-fg">{visibleChannelCount}/{namedChannels.length}</span>
    </span>
    <ChevronDown width="14" height="14" class="transition-transform {expanded ? '' : 'rotate-180'}" />
  </button>
</div>
