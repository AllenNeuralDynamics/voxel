<script lang="ts">
  import { ChevronDown } from '$lib/icons';
  import { SpinBox } from '$lib/prop/numeric';

  import { viewportFrameCovers } from './render';
  import type { AutoLevelsPreference, PreviewChannel, PreviewSession } from './session.svelte';

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
  let expandedChannelIdx = $state<number | null>(null);
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

  function dataTypeMax(channel: PreviewChannel): number {
    return 2 ** (channel.overviewFrame?.valid_bits ?? channel.viewportFrame?.valid_bits ?? 16) - 1;
  }

  function updateAutoLevel(channel: PreviewChannel, field: keyof AutoLevelsPreference, value: number): void {
    if (!channel.name) return;
    const current = channel.preferences.levels.auto;
    const next: AutoLevelsPreference = { ...current, [field]: value };
    previewer.setChannelAutoLevels(channel.name, next);
  }
</script>

<div class="flex flex-col gap-0.5">
  <div>
    <button
      type="button"
      class="flex h-7 w-full cursor-pointer items-center gap-2 px-3 text-sm text-fg-muted transition-colors hover:bg-element-hover hover:text-fg"
      aria-expanded={framesExpanded}
      onclick={() => (framesExpanded = !framesExpanded)}
    >
      <span class="flex-1 text-left">Frames</span>
      <ChevronDown width="13" height="13" class="shrink-0 transition-transform {framesExpanded ? '' : '-rotate-90'}" />
    </button>

    {#if framesExpanded}
      <div class="space-y-2 px-3 pb-2 text-sm">
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

  {#each namedChannels as channel (channel.idx)}
    {@const expanded = expandedChannelIdx === channel.idx}
    <div>
      <div class="flex h-8 w-full items-center px-1.5 text-sm text-fg-muted">
        <button
          type="button"
          class="flex h-full min-w-0 flex-1 cursor-pointer items-center gap-2 rounded px-1.5 text-left transition-colors hover:bg-element-hover hover:text-fg"
          aria-expanded={expanded}
          onclick={() => (expandedChannelIdx = expanded ? null : channel.idx)}
        >
          <span class="min-w-0 flex-1 truncate">{channel.label} levels</span>
        </button>
        <button
          type="button"
          class="h-6 shrink-0 cursor-pointer rounded px-1.5 text-sm transition-colors hover:bg-element-hover hover:text-fg disabled:cursor-not-allowed disabled:opacity-40"
          disabled={!channel.latestHistogram}
          aria-label="Apply auto levels to {channel.label}"
          title="Apply auto levels"
          onclick={() => channel.name && previewer.autoLevel(channel.name)}
        >
          Auto
        </button>
        <button
          type="button"
          class="flex size-6 shrink-0 cursor-pointer items-center justify-center rounded transition-colors hover:bg-element-hover hover:text-fg"
          aria-expanded={expanded}
          aria-label={expanded ? `Collapse ${channel.label}` : `Expand ${channel.label}`}
          onclick={() => (expandedChannelIdx = expanded ? null : channel.idx)}
        >
          <ChevronDown width="13" height="13" class="transition-transform {expanded ? '' : '-rotate-90'}" />
        </button>
      </div>

      {#if expanded}
        <div class="px-3 pb-2 text-sm">
          <div
            class="grid grid-cols-[2.75rem_minmax(0,1fr)_minmax(0,1fr)] items-center gap-x-1.5 gap-y-1.5 text-fg-muted"
          >
            <span>Black</span>
            <SpinBox
              model={{
                value: channel.preferences.levels.auto.lowPercentile,
                min: 0,
                max: channel.preferences.levels.auto.highPercentile - 0.01,
                step: 0.001,
                onChange: (value) => updateAutoLevel(channel, 'lowPercentile', value)
              }}
              decimals={3}
              numCharacters={5}
              suffix="%"
              align="right"
              steppers={false}
              class="w-full"
            />
            <SpinBox
              model={{
                value: channel.preferences.levels.auto.lowFloor,
                min: 0,
                max: Math.min(dataTypeMax(channel) - 1, channel.preferences.levels.auto.highCeiling - 1),
                step: 1,
                home: 0,
                onChange: (value) => updateAutoLevel(channel, 'lowFloor', value)
              }}
              decimals={0}
              numCharacters={5}
              prefix="≥"
              align="right"
              steppers={false}
              class="w-full"
            />

            <span>White</span>
            <SpinBox
              model={{
                value: channel.preferences.levels.auto.highPercentile,
                min: channel.preferences.levels.auto.lowPercentile + 0.01,
                max: 100,
                step: 0.001,
                onChange: (value) => updateAutoLevel(channel, 'highPercentile', value)
              }}
              decimals={3}
              numCharacters={5}
              suffix="%"
              align="right"
              steppers={false}
              class="w-full"
            />
            <SpinBox
              model={{
                value: channel.preferences.levels.auto.highCeiling,
                min: channel.preferences.levels.auto.lowFloor + 1,
                max: dataTypeMax(channel),
                step: 1,
                home: () => dataTypeMax(channel),
                onChange: (value) => updateAutoLevel(channel, 'highCeiling', value)
              }}
              decimals={0}
              numCharacters={5}
              prefix="≤"
              align="right"
              steppers={false}
              class="w-full"
            />
          </div>
        </div>
      {/if}
    </div>
  {/each}
</div>
