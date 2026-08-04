<script lang="ts">
  import { ChevronDown } from '$lib/icons';

  import { viewportFrameCovers } from './render';
  import type { PreviewChannel, PreviewSession } from './session.svelte';

  interface Props {
    previewer: PreviewSession;
  }

  interface ChannelSizes {
    channel: PreviewChannel;
    label: string;
    overview: string;
    viewport: string;
    sensor: string;
  }

  type SizeKey = 'overview' | 'viewport' | 'sensor';

  let { previewer }: Props = $props();
  let expanded = $state(false);
  let expandedSizes = $state<Record<SizeKey, boolean>>({ overview: false, viewport: false, sensor: false });

  const namedChannels = $derived(previewer.channels.filter((channel) => channel.name));
  const channelSizes = $derived.by<ChannelSizes[]>(() =>
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

  function summarize(key: SizeKey): string {
    const values = channelSizes.map((sizes) => sizes[key]);
    if (values.length === 0 || values.every((value) => value === '_')) return '_';
    return new Set(values).size === 1 ? values[0] : 'Mixed';
  }

  const sizeGroups = $derived([
    { key: 'overview' as const, label: 'Overview', value: summarize('overview') },
    { key: 'viewport' as const, label: 'Viewport', value: summarize('viewport') },
    { key: 'sensor' as const, label: 'Sensor', value: summarize('sensor') }
  ]);

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

<div>
  <button
    type="button"
    class="flex h-7 w-full cursor-pointer items-center justify-between px-3 text-sm text-fg-muted transition-colors hover:bg-element-hover hover:text-fg"
    aria-expanded={expanded}
    onclick={() => (expanded = !expanded)}
  >
    <span>Preview details</span>
    <ChevronDown width="13" height="13" class="transition-transform {expanded ? '' : '-rotate-90'}" />
  </button>

  {#if expanded}
    <div class="space-y-1 px-3 pb-2 text-sm">
      <div class="flex justify-between gap-2">
        <span class="text-fg-muted">Overview frame</span>
        <span class="font-mono tabular-nums">{overviewFrameIdx >= 0 ? overviewFrameIdx : '_'}</span>
      </div>
      <div class="flex justify-between gap-2 pb-1">
        <span class="text-fg-muted">Viewport frame</span>
        <span class="font-mono tabular-nums">{viewportFrameIdx >= 0 ? viewportFrameIdx : '_'}</span>
      </div>

      {#each sizeGroups as group (group.key)}
        {#if group.value === 'Mixed'}
          <button
            type="button"
            class="flex w-full cursor-pointer items-center justify-between gap-2 text-left hover:text-fg"
            aria-expanded={expandedSizes[group.key]}
            onclick={() => (expandedSizes[group.key] = !expandedSizes[group.key])}
          >
            <span class="text-fg-muted">{group.label}</span>
            <span class="flex items-center gap-1 font-mono">
              Mixed
              <ChevronDown
                width="12"
                height="12"
                class="transition-transform {expandedSizes[group.key] ? '' : '-rotate-90'}"
              />
            </span>
          </button>
          {#if expandedSizes[group.key]}
            <div class="space-y-0.5 border-l border-border pl-2">
              {#each channelSizes as sizes (sizes.channel.idx)}
                <div class="flex justify-between gap-2">
                  <span class="max-w-24 truncate text-fg-muted">{sizes.label}</span>
                  <span class="font-mono tabular-nums">{sizes[group.key]}</span>
                </div>
              {/each}
            </div>
          {/if}
        {:else}
          <div class="flex justify-between gap-2">
            <span class="text-fg-muted">{group.label}</span>
            <span class="font-mono tabular-nums">{group.value}</span>
          </div>
        {/if}
      {/each}
    </div>
  {/if}
</div>
