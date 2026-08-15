<script lang="ts">
  import { viewportFrameCovers } from './render';
  import type { PreviewSession } from './session.svelte';

  interface Props {
    previewer: PreviewSession;
  }

  let { previewer }: Props = $props();

  const namedChannels = $derived(previewer.channels.filter((c) => c.name));
  const channelFrames = $derived.by(() =>
    namedChannels.map((channel) => {
      const overview = channel.overviewFrame;
      const viewport = viewportFrameCovers(channel.viewportFrame, previewer.viewport, channel.rotationDeg)
        ? channel.viewportFrame
        : null;
      const sensor = overview ?? channel.viewportFrame;
      return {
        channel,
        label: channel.label ?? channel.name ?? '',
        overview: overview ? `#${overview.frame_idx} · ${overview.width}×${overview.height}` : '—',
        viewport: viewport ? `#${viewport.frame_idx} · ${viewport.width}×${viewport.height}` : '—',
        sensor: sensor ? `${sensor.sensor_width}×${sensor.sensor_height}` : '—'
      };
    })
  );

  const GROUPS: { key: 'overview' | 'viewport' | 'sensor'; label: string }[] = [
    { key: 'overview', label: 'Overview' },
    { key: 'viewport', label: 'Viewport' },
    { key: 'sensor', label: 'Sensor' }
  ];
</script>

<div class="space-y-2 text-sm">
  {#each GROUPS as group (group.key)}
    <div class="space-y-0.5">
      <div class="text-fg-muted">{group.label}</div>
      {#each channelFrames as frames (frames.channel.idx)}
        <div class="flex justify-between gap-4 pl-2">
          <span class="max-w-20 truncate text-fg-muted">{frames.label}</span>
          <span class="font-mono tabular-nums">{frames[group.key]}</span>
        </div>
      {/each}
    </div>
  {/each}
</div>
