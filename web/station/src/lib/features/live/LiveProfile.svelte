<script lang="ts">
  import { type Snippet, untrack } from 'svelte';

  import { getVoxelStation } from '$lib/context.svelte';
  import { AreaCamera } from '$lib/core/device.svelte';
  import ActivityButton from '$lib/features/live/ActivityButton.svelte';
  import LasersOff from '$lib/features/live/LasersOff.svelte';
  import LiveControls from '$lib/features/live/LiveControls.svelte';
  import PowerPane from '$lib/features/live/PowerPane.svelte';
  import ProfileSelect from '$lib/features/live/ProfileSelect.svelte';
  import StreamPane from '$lib/features/live/StreamPane.svelte';
  import { cn } from '@voxel/kit/cn';
  import { wavelengthToColor } from '@voxel/kit/colors';
  import { AutoSplit, createPaneSize, Pane, PaneDivider, PaneGroup, SplitView } from '@voxel/kit/pane';

  /**
   * The live profile: its bar (`start`, then the layout controls, the profile and the activity button), the image and the live controls,
   * and a footer panel for the stream and power, which a click on its bar opens; Lasers off sits at the bar's right
   * end. The workspace's side pane and the Live window both show it.
   */
  let {
    start,
    connected,
    dock
  }: {
    start: Snippet;
    connected: boolean;
    /** The footer panel's smallest height and the height it opens at, in rem. */
    dock: { min: number; start: number };
  } = $props();
  // Read once, as `createPaneSize` reads its bounds once.
  const { min: dockMin, start: dockStart } = untrack(() => dock);

  let controls = $state<Snippet>();

  // The footer: a panel for the stream and power, which a click on the bar opens and closes.
  let columnEl = $state<HTMLElement | null>(null);
  let streamRef = $state<Pane | undefined>(undefined);
  const streamPanel = createPaneSize(() => columnEl, {
    collapsed: 0,
    min: dockMin,
    default: dockStart,
    fallback: { collapsed: 0, min: 15, default: 30 },
    persist: 'live-footer'
  });
  // The image and the light settings keep at least half the column while the footer panel is dragged.
  const mainSize = createPaneSize(() => columnEl, {
    get min() {
      const rem = parseFloat(getComputedStyle(document.documentElement).fontSize);
      return (columnEl?.getBoundingClientRect().height ?? 0) / rem / 2;
    },
    fallback: { min: 50 }
  });
  const streamOpen = $derived(streamRef ? !streamRef.isCollapsed() : false);

  // The bar's summaries: the slowest camera stream with all dropped frames, and the lights that are on.
  const station = getVoxelStation();
  const instrument = $derived(station.instrument);
  const streams = $derived(
    (instrument?.devicesOf(AreaCamera) ?? []).flatMap((camera) => (camera.streamInfo ? [camera.streamInfo] : []))
  );
  const slowest = $derived(streams.toSorted((a, b) => a.frame_rate_fps - b.frame_rate_fps).at(0));
  const dropped = $derived(streams.reduce((sum, stream) => sum + stream.dropped_frames, 0));
  const lit = $derived((instrument?.beams ?? []).filter((beam) => beam.source.isOn));

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
            <LiveControls />
          </section>{/snippet}
      </SplitView>
    </Pane>
    <PaneDivider ondblclick={() => streamRef && streamPanel.toggle(streamRef)} />
    <Pane bind:this={streamRef} {...streamPanel} defaultSize={0} collapsible class="min-h-0 bg-pane">
      <!-- Stream beside Power while both fit, else above it, so each sits over its summary in the bar. -->
      <AutoSplit
        persist="live-dock"
        panes={{
          stream: { horizontal: { min: 24 }, vertical: { min: 5 } },
          power: { horizontal: { min: 18, default: 22, max: 32 }, vertical: { min: 5, default: 8 } }
        }}
      >
        {#snippet stream()}<StreamPane />{/snippet}
        {#snippet power()}<PowerPane />{/snippet}
      </AutoSplit>
    </Pane>
  </PaneGroup>
  <footer aria-label="Stream and power">
    <!-- The bar opens and closes the panel; Lasers off is its own button at the right end. -->
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
        <!-- The slowest stream, with the frames dropped; then the lights that are on. -->
        <span class="flex min-w-0 flex-1 items-center gap-2 whitespace-nowrap tabular-nums">
          {#if slowest}
            <span>{slowest.frame_rate_fps.toFixed(1)} fps</span>
            {#if dropped > 0}<span class="text-warning-fg">{dropped} dropped</span>{/if}
          {/if}
        </span>
        <span class="flex shrink-0 items-center gap-1.5 whitespace-nowrap">
          {#each lit as beam (beam.source.id)}
            {@const color = wavelengthToColor(beam.source.wavelength)}
            <!-- Filled: the light reaches the sample. Faint: the laser is on, but something stops its light. -->
            <span
              class="size-2.5 rounded-full border-2"
              style:border-color={color}
              style:background-color={beam.reaches ? color : `color-mix(in oklab, ${color} 30%, transparent)`}
              aria-hidden="true"
            ></span>
          {/each}
          {#if instrument}
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
