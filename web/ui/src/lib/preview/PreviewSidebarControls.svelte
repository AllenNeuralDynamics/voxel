<script lang="ts">
  import { ChevronDown } from '$lib/icons';

  import PreviewChannelPrefs from './PreviewChannelPrefs.svelte';
  import { viewportFrameCovers } from './render';
  import type { PreviewChannel, PreviewSession } from './session.svelte';

  interface Props {
    previewer: PreviewSession;
  }

  interface ChannelFrames {
    channel: PreviewChannel;
    label: string;
    overview: string;
    viewport: string;
    sensor: string;
  }

  let { previewer }: Props = $props();
  let framesExpanded = $state(false);

  const namedChannels = $derived(previewer.channels.filter((channel) => channel.name));
  const channelFrames = $derived.by<ChannelFrames[]>(() =>
    namedChannels.map((channel) => {
      const overview = channel.overviewFrame;
      const viewport = viewportFrameCovers(channel.viewportFrame, previewer.viewport, channel.rotationDeg)
        ? channel.viewportFrame
        : null;
      const sensor = overview ?? channel.viewportFrame;
      return {
        channel,
        label: channel.label ?? channel.name ?? '',
        overview: overview ? `#${overview.frame_idx} · ${overview.width}×${overview.height}` : '_',
        viewport: viewport ? `#${viewport.frame_idx} · ${viewport.width}×${viewport.height}` : '_',
        sensor: sensor ? `${sensor.sensor_width}×${sensor.sensor_height}` : '_'
      };
    })
  );
</script>

<div class="flex flex-col">
  <div class="flex w-full items-center px-2 py-1 text-sm text-fg-muted">Channels</div>
  <div class="">
    {#each namedChannels as channel (channel.idx)}
      <div class="px-2.5 py-1">
        <PreviewChannelPrefs {previewer} {channel} />
      </div>
    {/each}
  </div>
  <div class="border-t border-border">
    <button
      type="button"
      class="flex h-7 w-full cursor-pointer items-center gap-2 px-2 text-sm text-fg-muted transition-colors hover:bg-element-hover hover:text-fg"
      aria-expanded={framesExpanded}
      onclick={() => (framesExpanded = !framesExpanded)}
    >
      <span class="flex-1 text-left">Frames Info</span>
      <ChevronDown width="13" height="13" class="shrink-0 transition-transform {framesExpanded ? '' : '-rotate-90'}" />
    </button>

    {#if framesExpanded}
      <div class="space-y-2 px-2 pb-2 text-sm">
        {#each [{ key: 'overview' as const, label: 'Overview' }, { key: 'viewport' as const, label: 'Viewport' }, { key: 'sensor' as const, label: 'Sensor' }] as group (group.key)}
          <div class="space-y-0.5">
            <div class="text-fg-muted">{group.label}</div>
            {#each channelFrames as frames (frames.channel.idx)}
              <div class="flex justify-between gap-2 pl-2">
                <span class="max-w-20 truncate text-fg-muted">{frames.label}</span>
                <span class="font-mono text-sm tabular-nums">{frames[group.key]}</span>
              </div>
            {/each}
          </div>
        {/each}
      </div>
    {/if}
  </div>
</div>
