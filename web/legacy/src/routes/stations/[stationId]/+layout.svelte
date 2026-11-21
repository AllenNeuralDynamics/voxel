<script lang="ts">
  import { useEventListener } from 'runed';
  import { onMount } from 'svelte';

  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { provideStationContext } from '$lib/context.svelte';
  import { resolveInstrumentView } from '$lib/core/model';
  import { instrumentNavigation } from '$lib/navigation';
  import { activateDashboardWindow, isStationWindowRequest, stationWindowName } from '$lib/shell/app-windows';
  import CloseInstrumentDialog from '$lib/shell/CloseInstrumentDialog.svelte';
  import ConnectionSplash from '$lib/shell/ConnectionSplash.svelte';
  import DeckPane from '$lib/shell/DeckPane.svelte';
  import * as Rail from '$lib/shell/rail';
  import { InstrumentSelection } from '$lib/shell/selection.svelte';
  import StationMenu from '$lib/shell/StationMenu.svelte';
  import ViewerPane from '$lib/shell/ViewerPane.svelte';
  import VoxelLogo from '$lib/shell/VoxelLogo.svelte';
  import { reportFailure } from '@voxel/kit/failures';
  import { displayName } from '@voxel/kit/format';
  import { createPaneSize, Pane, PaneGroup } from '@voxel/kit/pane';
  import { PaneDivider } from '@voxel/kit/pane';

  import type { LayoutProps } from './$types';

  let { children, params }: LayoutProps = $props();

  const app = provideStationContext();
  const selection = new InstrumentSelection(app, () => params);

  onMount(() => {
    window.name = stationWindowName(params.stationId);
    void start();
  });
  useEventListener(window, 'message', (event) => {
    if (event.origin !== window.location.origin || !isStationWindowRequest(event.data)) return;
    if (event.data.stationId !== params.stationId) return;
    selection.receive({ instrumentId: event.data.instrumentId, open: event.data.open });
  });

  async function start(): Promise<void> {
    try {
      await app.initialize(params.stationId);
      await selection.start();
    } catch (error) {
      reportFailure(error);
    }
  }

  const navigation = $derived.by(() => {
    const id = selection.selected ?? app.activeName;
    if (!id) return null;
    return instrumentNavigation({
      stationId: params.stationId,
      instrumentId: id,
      saved: resolveInstrumentView(app.discovery, { kind: 'instrument', name: id }),
      open: app.activeName === id && !!app.instrument
    });
  });
  const stationName = $derived(app.discovery.station.name || displayName(params.stationId));

  function showDashboard(): void {
    const href = resolve(`/(dashboard)/stations?station=${encodeURIComponent(params.stationId)}`);
    if (activateDashboardWindow(href)) return;
    void goto(href, { keepFocus: true, noScroll: true });
  }

  const barSplits = [{ size: 'var(--app-bar-height)', gap: '0.875rem' }, {}];

  // The logo opens the station menu, like the station name next to it.
  let stationMenuOpen = $state(false);

  let frameRef = $state<HTMLElement | null>(null);
  const contentPane = createPaneSize(() => frameRef, {
    min: 32,
    max: 48,
    default: 32,
    fallback: { min: 30, default: 30 },
    persist: 'work'
  });
  const viewerPane = createPaneSize(() => frameRef, {
    min: 48,
    fallback: { min: 40 }
  });
  const deckPane = createPaneSize(() => frameRef, {
    min: 30,
    default: 34,
    max: 34,
    fallback: { min: 15, max: 15 }
  });
</script>

<svelte:head>
  <title>Voxel — {stationName}</title>
</svelte:head>

{#if !app.client.isConnected || !app.ready}
  <ConnectionSplash />
{:else}
  <div class="flex h-screen w-screen overflow-hidden text-fg">
    <div class="grid shrink-0 grid-rows-[auto_minmax(0,1fr)]">
      <button
        type="button"
        class="group app-bar w-rail cursor-pointer justify-center border-r focus-visible:outline-none"
        title="Station menu"
        aria-label="Station menu"
        aria-haspopup="menu"
        aria-expanded={stationMenuOpen}
        data-opens-station-menu
        onclick={() => {
          if (!app.instrumentTransition) stationMenuOpen = !stationMenuOpen;
        }}
      >
        <span
          class="rounded-xl p-1.5 group-hover:bg-tint group-focus-visible:outline-2 group-focus-visible:outline-focus"
        >
          <VoxelLogo class="size-6" />
        </span>
      </button>
      <Rail.Root aria-label="Instrument navigation">
        {#if navigation}
          {#each navigation.groups as items, index (index)}
            <Rail.Group>
              {#each items as item (item.href)}
                <Rail.Item {...item} />
              {/each}
            </Rail.Group>
          {/each}
          <Rail.Group class="mt-auto">
            <Rail.Item {...navigation.settings} />
          </Rail.Group>
        {/if}
      </Rail.Root>
    </div>
    <PaneGroup direction="horizontal" bind:ref={frameRef} class="h-full min-w-0 flex-1 bg-shell text-fg">
      <Pane {...contentPane} class="grid min-w-0 grid-rows-[auto_minmax(0,1fr)]">
        <div class="app-bar pr-4">
          <StationMenu
            bind:open={stationMenuOpen}
            stationId={params.stationId}
            {stationName}
            selectedInstrumentId={selection.selected ?? app.activeName}
            disabled={app.instrumentTransition}
            onselectinstrument={(stationId, instrumentId) => selection.select(stationId, instrumentId)}
            onclose={() => selection.askToClose()}
            ondashboard={showDashboard}
          />
        </div>
        <main class="flex min-h-0 min-w-0 flex-col overflow-hidden bg-pane">
          {@render children()}
        </main>
      </Pane>
      <PaneDivider direction="vertical" splits={barSplits} />
      <Pane {...viewerPane} role="region" aria-label="Viewer" class="grid min-w-0 grid-rows-[auto_minmax(0,1fr)]">
        <ViewerPane instrumentId={selection.current} />
      </Pane>
      {#if app.instrument}
        <PaneDivider direction="vertical" splits={barSplits} />
        <Pane
          {...deckPane}
          role="region"
          aria-label="Live controls"
          class="grid min-w-0 grid-rows-[auto_minmax(0,1fr)] bg-pane"
        >
          <DeckPane instrument={app.instrument} />
        </Pane>
      {/if}
    </PaneGroup>
  </div>
  <CloseInstrumentDialog {selection} />
{/if}
