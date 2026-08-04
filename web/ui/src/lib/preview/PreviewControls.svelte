<script lang="ts">
  import { Popover } from 'bits-ui';

  import { emissionToPreviewColor } from '$lib/colors.svelte';
  import { ChevronDown } from '$lib/icons';
  import { type Preview } from '$lib/model';

  import Histogram from './Histogram.svelte';
  import { viewportFrameCovers } from './render';

  interface Props {
    previewer: Preview;
  }

  let { previewer }: Props = $props();

  let expanded = $state(true);

  const namedChannels = $derived(previewer.channels.filter((c) => c.name));
  const channelSizes = $derived.by(() =>
    namedChannels.map((channel) => {
      const overview = channel.overviewFrame;
      const viewport = viewportFrameCovers(channel.viewportFrame, previewer.viewport, channel.rotationDeg)
        ? channel.viewportFrame
        : null;
      const sensor = overview ?? channel.viewportFrame;
      return {
        channel,
        label: channel.label ?? channel.name ?? '',
        overview: overview ? `${overview.width}×${overview.height}` : '_',
        viewport: viewport ? `${viewport.width}×${viewport.height}` : '_',
        sensor: sensor ? `${sensor.sensor_width}×${sensor.sensor_height}` : '_'
      };
    })
  );

  function summarize(values: string[]): string {
    if (values.length === 0 || values.every((value) => value === '_')) return '_';
    return new Set(values).size === 1 ? values[0] : 'Mixed';
  }

  const overviewSize = $derived(summarize(channelSizes.map((sizes) => sizes.overview)));
  const viewportSize = $derived(summarize(channelSizes.map((sizes) => sizes.viewport)));
  const sensorSize = $derived(summarize(channelSizes.map((sizes) => sizes.sensor)));
  const hasMixedSizes = $derived([overviewSize, viewportSize, sensorSize].includes('Mixed'));
  const overviewFrameIdx = $derived(
    Math.max(-1, ...namedChannels.map((channel) => channel.overviewFrame?.frame_idx ?? -1))
  );
  const viewportFrameIdx = $derived(
    Math.max(
      -1,
      ...namedChannels.map((channel) =>
        viewportFrameCovers(channel.viewportFrame, previewer.viewport, channel.rotationDeg)
          ? (channel.viewportFrame?.frame_idx ?? -1)
          : -1
      )
    )
  );
</script>

{#snippet sizeRows()}
  <div class="space-y-1 py-2">
    {#each [['Overview', overviewSize], ['Viewport', viewportSize], ['Sensor', sensorSize]] as [label, value] (label)}
      <div class="flex justify-between gap-2">
        <span class="text-fg-muted">{label}</span>
        <span class="text-right tabular-nums" class:text-fg={value === 'Mixed'}>{value}</span>
      </div>
    {/each}
  </div>
{/snippet}

<div class="pointer-events-auto flex w-64 flex-col items-start overlay-panel">
  {#if expanded}
    <div class="flex w-64 flex-col divide-y divide-border overflow-hidden border-b border-border px-2.5">
      {#if hasMixedSizes}
        <Popover.Root>
          <Popover.Trigger
            class="block w-full cursor-pointer text-left"
            aria-label="Show per-channel preview dimensions"
          >
            {@render sizeRows()}
          </Popover.Trigger>
          <Popover.Portal>
            <Popover.Content
              side="right"
              align="start"
              sideOffset={6}
              class="z-50 rounded border border-border bg-floating p-2 shadow-xl outline-none"
            >
              <table class="border-collapse font-mono text-xs whitespace-nowrap">
                <thead class="text-fg-muted">
                  <tr>
                    <th class="px-1.5 py-1 text-left font-normal">Channel</th>
                    <th class="px-1.5 py-1 text-right font-normal">Overview</th>
                    <th class="px-1.5 py-1 text-right font-normal">Viewport</th>
                    <th class="px-1.5 py-1 text-right font-normal">Sensor</th>
                  </tr>
                </thead>
                <tbody class="text-fg">
                  {#each channelSizes as sizes (sizes.channel.idx)}
                    <tr class="border-t border-border">
                      <td class="max-w-32 truncate px-1.5 py-1">{sizes.label}</td>
                      <td class="px-1.5 py-1 text-right tabular-nums">{sizes.overview}</td>
                      <td class="px-1.5 py-1 text-right tabular-nums">{sizes.viewport}</td>
                      <td class="px-1.5 py-1 text-right tabular-nums">{sizes.sensor}</td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </Popover.Content>
          </Popover.Portal>
        </Popover.Root>
      {:else}
        {@render sizeRows()}
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
            colormapPreference={channel.colormapPreference}
            autoColormap={emissionToPreviewColor(channel.config?.emission)}
            colormap={channel.resolvedColormap}
            catalog={previewer.catalog}
            onColormapChange={(cmap) => {
              if (channel.name) previewer.setChannelColormap(channel.name, cmap);
            }}
            dataTypeMax={2 ** (channel.overviewFrame?.valid_bits ?? 16) - 1}
            visible={channel.visible}
            onVisibilityChange={(v) => {
              if (channel.name) previewer.setChannelVisible(channel.name, v);
            }}
          />
        </div>
      {/each}
    </div>
  {/if}

  <button
    onclick={() => (expanded = !expanded)}
    class="flex h-7 w-full cursor-pointer items-center justify-between gap-1.5 px-2 font-mono text-fg-muted transition-colors hover:bg-element-hover hover:text-fg"
    aria-label={expanded ? 'Hide histograms' : 'Show histograms'}
    title={expanded ? 'Hide histograms' : 'Show histograms'}
  >
    {#if overviewFrameIdx >= 0}
      <span>
        Frame O <span class="text-fg">{overviewFrameIdx}</span> · V
        <span class="text-fg">{viewportFrameIdx >= 0 ? viewportFrameIdx : '_'}</span>
      </span>
    {:else}
      <span>No frames</span>
    {/if}
    <ChevronDown width="14" height="14" class="transition-transform {expanded ? '' : 'rotate-180'}" />
  </button>
</div>
