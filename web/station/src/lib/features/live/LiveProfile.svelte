<script lang="ts">
  import { type Snippet, untrack } from 'svelte';

  import { getChannelPrefs, getVoxelStation } from '$lib/context.svelte';
  import { AreaCamera } from '$lib/core/device.svelte';
  import ActivityButton from '$lib/features/live/ActivityButton.svelte';
  import LasersOff from '$lib/features/live/LasersOff.svelte';
  import type { DeviceLink } from '$lib/features/live/live-dock.svelte';
  import LiveControls from '$lib/features/live/LiveControls.svelte';
  import PowerPane from '$lib/features/live/PowerPane.svelte';
  import StreamPane from '$lib/features/live/StreamPane.svelte';
  import ProfileSelect from '$lib/features/profiles/ProfileSelect.svelte';
  import { cn } from '@voxel/kit/cn';
  import { wavelengthToColor } from '@voxel/kit/colors';
  import { displayName } from '@voxel/kit/format';
  import { AutoSplit, createPaneSize, Pane, PaneDivider, PaneGroup, SplitView } from '@voxel/kit/pane';

  /** The live image and controls, shown in the workspace side pane or the Live window. */
  let {
    start,
    connected,
    deviceLink,
    dock
  }: {
    start: Snippet;
    connected: boolean;
    /** The workspace and the Live window reach a device page differently. */
    deviceLink: DeviceLink;
    /** In rem. */
    dock: { min: number; start: number };
  } = $props();
  // Read once, as `createPaneSize` reads its bounds once.
  const { min: dockMin, start: dockStart } = untrack(() => dock);

  let controls = $state<Snippet>();

  let columnEl = $state<HTMLElement | null>(null);
  let streamRef = $state<Pane | undefined>(undefined);
  const streamPanel = createPaneSize(() => columnEl, {
    collapsed: 0,
    min: dockMin,
    default: dockStart,
    fallback: { collapsed: 0, min: 15, default: 30 },
    persist: 'live-footer'
  });
  const mainSize = createPaneSize(() => columnEl, {
    get min() {
      const rem = parseFloat(getComputedStyle(document.documentElement).fontSize);
      return (columnEl?.getBoundingClientRect().height ?? 0) / rem / 2;
    },
    fallback: { min: 50 }
  });
  const streamOpen = $derived(streamRef ? !streamRef.isCollapsed() : false);

  const station = getVoxelStation();
  const session = $derived(station.session);
  const prefs = getChannelPrefs();
  // Each camera of the active profile, in its display color, with its stream while it streams.
  const cameras = $derived.by(() => {
    const profileId = session?.activeProfile;
    const profile = profileId ? session?.instrument.state.profile(profileId) : undefined;
    if (!profileId || !profile) return [];
    return Object.entries(profile.channels).flatMap(([channel, byCamera]) =>
      Object.keys(byCamera).map((id) => {
        const device = session?.device(id);
        return {
          id,
          color: prefs.color(profileId, channel, id),
          stream: device instanceof AreaCamera ? device.streamInfo : undefined
        };
      })
    );
  });
  const streaming = $derived(cameras.filter((camera) => camera.stream).length);
  const dropping = $derived(cameras.filter((camera) => (camera.stream?.dropped_frames ?? 0) > 0).length);
  const lit = $derived((session?.beams ?? []).filter((beam) => beam.source.isOn));

  function toggleStreamPanel(): void {
    if (streamRef) streamPanel.toggle(streamRef);
  }
</script>

<div class="grid h-full min-w-0 grid-rows-[auto_minmax(0,1fr)_auto] bg-pane">
  <div class="pr-inset app-bar min-w-0 gap-2">
    {@render start()}
    <span class="min-w-3 flex-1"></span>
    {@render controls?.()}
    <ProfileSelect />
    <ActivityButton />
  </div>
  <PaneGroup direction="vertical" bind:ref={columnEl} class="min-h-0">
    <Pane class="min-h-0" {...mainSize}>
      <SplitView
        class="min-h-0"
        panes={{
          image: { horizontal: { min: 30 }, vertical: { min: 15 } },
          settings: { horizontal: { min: 28, default: 32, max: 48 }, vertical: { min: 12 } }
        }}
        persist="live-profile"
        bind:controls
      >
        {#snippet image()}<section
            class="bg-image h-full"
            aria-label="Live view"
            inert={!connected}
          ></section>{/snippet}
        {#snippet settings()}<section class="h-full" aria-label="Live controls" inert={!connected}>
            <LiveControls {deviceLink} />
          </section>{/snippet}
      </SplitView>
    </Pane>
    <PaneDivider ondblclick={() => streamRef && streamPanel.toggle(streamRef)} />
    <Pane bind:this={streamRef} {...streamPanel} defaultSize={0} collapsible class="min-h-0 bg-pane">
      <!-- Side by side when they fit, so each sits over its summary in the bar. -->
      <AutoSplit
        persist="live-dock"
        panes={{
          stream: { horizontal: { min: 28 }, vertical: { min: 5 } },
          power: { horizontal: { min: 18, default: 30, max: 40 }, vertical: { min: 5, default: 8 } }
        }}
      >
        {#snippet stream()}<StreamPane {deviceLink} />{/snippet}
        {#snippet power()}<PowerPane {deviceLink} />{/snippet}
      </AutoSplit>
    </Pane>
  </PaneGroup>
  <footer aria-label="Stream and power">
    <div class="status-bar">
      <button
        type="button"
        class={cn(
          'px-inset flex h-full min-w-0 flex-1 cursor-pointer items-center gap-3 text-sm hover:bg-tint',
          streamOpen && 'bg-tint'
        )}
        aria-expanded={streamOpen}
        onclick={toggleStreamPanel}
      >
        <span class="flex min-w-0 flex-1 items-center gap-2 whitespace-nowrap tabular-nums">
          {#each cameras as camera (camera.id)}
            {@const dropped = camera.stream?.dropped_frames ?? 0}
            <!-- Filled: it streams. Ring: idle. The warning color: it drops frames. -->
            <span
              class="size-2 rounded-[1px] border"
              style:border-color={dropped > 0 ? 'var(--warning-fg)' : camera.color}
              style:background-color={camera.stream
                ? dropped > 0
                  ? 'var(--warning-fg)'
                  : camera.color
                : 'transparent'}
              title={camera.stream
                ? `${displayName(camera.id)}: ${camera.stream.frame_rate_fps.toFixed(1)} fps, ${dropped} dropped`
                : `${displayName(camera.id)}: idle`}
              role="img"
              aria-label={camera.stream
                ? `${displayName(camera.id)}: ${camera.stream.frame_rate_fps.toFixed(1)} fps, ${dropped} dropped`
                : `${displayName(camera.id)}: idle`}
            ></span>
          {/each}
          {#if cameras.length > 0}
            {#if dropping > 0}
              <span class="text-warning-fg">{dropping} dropping</span>
            {:else}
              <span class={cn(streaming === 0 && 'text-fg-faint')}
                >{streaming === 0 ? 'Idle' : `${streaming} streaming`}</span
              >
            {/if}
          {/if}
        </span>
        <span class="flex shrink-0 items-center gap-1.5 whitespace-nowrap">
          {#each lit as beam (beam.source.id)}
            {@const color = wavelengthToColor(beam.source.wavelength)}
            <!-- Faint: laser on, but its light is blocked downstream. -->
            <span
              class="size-2.5 rounded-full border-2"
              style:border-color={color}
              style:background-color={beam.reaches ? color : `color-mix(in oklab, ${color} 30%, transparent)`}
              aria-hidden="true"
            ></span>
          {/each}
          {#if session}
            <span class={cn(lit.length === 0 && 'text-fg-faint')}
              >{lit.length === 0 ? 'All off' : `${lit.filter((beam) => beam.reaches).length} on`}</span
            >
          {/if}
        </span>
      </button>
      <span class="pr-inset flex h-full items-center pl-1"><LasersOff /></span>
    </div>
  </footer>
</div>
