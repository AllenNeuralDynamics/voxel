<script lang="ts">
  import { onDestroy, onMount, type Snippet } from 'svelte';

  import { afterNavigate, goto } from '$app/navigation';
  import { page } from '$app/state';
  import { provideInstrumentSelection, provideStationContext } from '$lib/context.svelte';
  import type { ConnectionState } from '$lib/model/client.svelte';
  import * as Rail from '$lib/shell/rail';
  import StationMenu from '$lib/shell/StationMenu.svelte';
  import VoxelLogo from '$lib/shell/VoxelLogo.svelte';
  import { DropdownMenu } from '@voxel/kit';
  import { cn } from '@voxel/kit/cn';
  import { displayName } from '@voxel/kit/format';
  import {
    Activity,
    Bug,
    ChartNoAxesColumn,
    Cpu,
    FileCog,
    History,
    Play,
    Radio,
    RadioOff,
    Route,
    Settings
  } from '@voxel/kit/icons';
  import { createPaneSize, Pane, PaneDivider, PaneGroup, SplitView } from '@voxel/kit/pane';
  import { pref } from '@voxel/kit/pref';
  import { ModeSwitch } from '@voxel/kit/style';

  import type { LayoutProps } from './$types';

  let { children, params }: LayoutProps = $props();

  const station = provideStationContext();
  const selection = provideInstrumentSelection(station, () => params);
  onMount(() => station.initialize(params.stationId));
  onDestroy(() => station.dispose());

  const home = $derived(`/stations/${params.stationId}`);
  // The instrument pages. Without a selected instrument they have no address yet, so the rail leaves them out.
  const places = $derived.by(() => {
    const name = selection.selected;
    if (!name) return [];
    return [
      { href: selection.href(name, 'run'), label: 'Run', icon: Play },
      { href: selection.href(name, 'history'), label: 'History', icon: History },
      { href: selection.href(name, 'light'), label: 'Light', icon: Route },
      { href: selection.href(name, 'timing'), label: 'Timing', icon: Activity },
      { href: selection.href(name, 'profiles'), label: 'Profiles', icon: ChartNoAxesColumn },
      { href: selection.href(name, 'devices'), label: 'Devices', icon: Cpu },
      { href: selection.href(name, 'config'), label: 'Config', icon: FileCog }
    ];
  });

  // The pages that work only on the open instrument. Showing another instrument, they are inert.
  const livePlaces = ['run', 'light', 'timing', 'devices'];
  const openName = $derived(station.session?.instrument_name ?? null);
  const notOpen = $derived(
    params.instrument !== undefined &&
      params.instrument !== station.session?.instrument_name &&
      livePlaces.includes(page.route.id?.split('/').at(-1) ?? '')
  );

  let frameRef = $state<HTMLElement | null>(null);
  // As the prototype: the page starts at most 80rem wide and the Live profile takes the rest, at least 34rem. A drag
  // then sets the page's width, from 36rem up to what leaves the Live profile 30rem.
  const pagePane = createPaneSize(() => frameRef, {
    min: 36,
    get default() {
      const rem = parseFloat(getComputedStyle(document.documentElement).fontSize);
      return Math.min(80, (frameRef?.getBoundingClientRect().width ?? 0) / rem - 34);
    },
    fallback: { min: 30, default: 60 },
    persist: 'page'
  });
  const livePane = createPaneSize(() => frameRef, { min: 30, fallback: { min: 25 } });

  let liveControls = $state<Snippet>();

  // The link to the station, in the rail's corner. While not connected, what acts on the station is inert; moving
  // between pages, the bars and their panels still work.
  const connections: Record<ConnectionState, { label: string; tone: string }> = {
    idle: { label: 'Not connected', tone: 'text-fg-muted' },
    connecting: { label: 'Connecting…', tone: 'animate-pulse text-warning-fg' },
    connected: { label: 'Connected to the station', tone: 'text-fg-muted' },
    reconnecting: { label: 'Reconnecting…', tone: 'animate-pulse text-warning-fg' },
    'service-stopped': { label: 'Station service stopped', tone: 'text-danger-fg' },
    'server-down': { label: 'No connection to the server', tone: 'text-danger-fg' }
  };
  const connection = $derived(station.client.state);
  const connected = $derived(connection === 'connected');

  // The page's footer: a panel above the Log and Issues tabs, which opens on a tab and closes on the open tab. Both
  // footers start closed and open at their saved height. Diagnostics is the same panel over the whole page; closing
  // it, or going to another page, puts the panel back as it was.
  let pageColumnEl = $state<HTMLElement | null>(null);
  let bodyRef = $state<Pane | undefined>(undefined);
  let logRef = $state<Pane | undefined>(undefined);
  const body = createPaneSize(() => pageColumnEl, { collapsed: 0, min: 12, fallback: { collapsed: 0, min: 20 } });
  const logPanel = createPaneSize(() => pageColumnEl, {
    collapsed: 0,
    min: 8,
    default: 17,
    fallback: { collapsed: 0, min: 15, default: 30 },
    persist: 'page-footer'
  });
  const logTab = pref<'log' | 'issues'>('page-footer:tab', 'log');
  const logOpen = $derived(logRef ? !logRef.isCollapsed() : false);
  const diagnostics = $derived(bodyRef ? bodyRef.isCollapsed() : false);
  let openBeforeDiagnostics = false;

  function pickLogTab(tab: 'log' | 'issues'): void {
    if (!logRef) return;
    const open = logOpen && logTab.get() === tab;
    logTab.set(tab);
    if (open || !logOpen) logPanel.toggle(logRef);
  }

  function toggleDiagnostics(): void {
    if (!bodyRef || !logRef) return;
    if (diagnostics) {
      bodyRef.expand();
      if (!openBeforeDiagnostics) logRef.collapse();
      return;
    }
    openBeforeDiagnostics = logOpen;
    if (!logOpen) logPanel.toggle(logRef);
    bodyRef.collapse();
  }

  afterNavigate(() => {
    if (diagnostics) toggleDiagnostics();
  });

  // The Live profile's footer: a panel above the Power and Stream tabs, which works as the page's.
  let liveColumnEl = $state<HTMLElement | null>(null);
  let streamRef = $state<Pane | undefined>(undefined);
  const streamPanel = createPaneSize(() => liveColumnEl, {
    collapsed: 0,
    min: 8,
    default: 17,
    fallback: { collapsed: 0, min: 15, default: 30 },
    persist: 'live-footer'
  });
  const streamTab = pref<'power' | 'stream'>('live-footer:tab', 'stream');
  const streamOpen = $derived(streamRef ? !streamRef.isCollapsed() : false);

  function pickStreamTab(tab: 'power' | 'stream'): void {
    if (!streamRef) return;
    const open = streamOpen && streamTab.get() === tab;
    streamTab.set(tab);
    if (open || !streamOpen) streamPanel.toggle(streamRef);
  }
</script>

<div class="flex h-screen w-screen overflow-hidden text-fg">
  <div class="grid shrink-0 grid-rows-[auto_minmax(0,1fr)_auto]">
    <div class="app-bar w-rail justify-center border-r px-1.5">
      <DropdownMenu.Root>
        <DropdownMenu.Trigger
          class="grid h-ui-md w-full place-items-center rounded-xl hover:bg-tint data-[state=open]:bg-tint"
          aria-label="Voxel menu"
        >
          <VoxelLogo class="size-6" />
        </DropdownMenu.Trigger>
        <DropdownMenu.Content side="bottom" align="start" sideOffset={4} class="w-52">
          <DropdownMenu.Item onclick={() => goto(`${home}/settings`)}>
            <Settings class="size-4" aria-hidden="true" />
            Settings
          </DropdownMenu.Item>
          <DropdownMenu.Separator />
          <ModeSwitch />
        </DropdownMenu.Content>
      </DropdownMenu.Root>
    </div>
    <Rail.Root aria-label="Places">
      <Rail.Group>
        {#each places as place (place.href)}
          <Rail.Item {...place} />
        {/each}
      </Rail.Group>
    </Rail.Root>
    <button
      type="button"
      class={cn('status-bar w-rail justify-center border-r hover:bg-element-hover', connections[connection].tone)}
      title={connections[connection].label}
      aria-label={connections[connection].label}
      onclick={() => !connected && station.client.retry()}
    >
      {#if connected}
        <Radio class="size-5 **:stroke-[1.25]" aria-hidden="true" />
      {:else}
        <RadioOff class="size-5 **:stroke-[1.25]" aria-hidden="true" />
      {/if}
    </button>
  </div>
  <PaneGroup direction="horizontal" bind:ref={frameRef} class="h-full min-w-0 flex-1 bg-shell text-fg">
    <Pane {...pagePane} class="grid min-w-0 grid-rows-[auto_minmax(0,1fr)_auto]">
      <div class="app-bar px-4">
        <StationMenu {selection} />
      </div>
      <PaneGroup direction="vertical" bind:ref={pageColumnEl} class="min-h-0">
        <Pane bind:this={bodyRef} {...body} collapsible class="min-h-0">
          <main class="flex h-full min-h-0 min-w-0 flex-col overflow-hidden bg-pane" inert={!connected || notOpen}>
            {@render children()}
          </main>
        </Pane>
        <PaneDivider ondblclick={() => logRef && logPanel.toggle(logRef)} />
        <Pane bind:this={logRef} {...logPanel} defaultSize={0} collapsible class="min-h-0 bg-pane">
          {#if diagnostics}
            <div class="grid h-full grid-cols-[minmax(0,22rem)_minmax(0,1fr)]" aria-label="Diagnostics">
              <div class="flex flex-col border-r border-line-faint">
                {#each ['Alerts', 'Setup problems', 'Earlier'] as heading (heading)}
                  <h2 class="px-4 pt-3 pb-1 text-sm font-medium">{heading}</h2>
                {/each}
              </div>
              <h2 class="px-4 pt-3 pb-1 text-sm font-medium">Log</h2>
            </div>
          {:else}
            <div class="h-full" role="tabpanel" aria-label={logTab.get() === 'log' ? 'Log' : 'Issues'}></div>
          {/if}
        </Pane>
      </PaneGroup>
      <footer aria-label="Log and issues">
        <div class="status-bar gap-[0.15rem] pr-[0.85rem] pl-[0.6rem]" role="tablist">
          {@render tab('Log', logOpen && logTab.get() === 'log', () => pickLogTab('log'))}
          {@render tab('Issues', logOpen && logTab.get() === 'issues', () => pickLogTab('issues'))}
          <button
            type="button"
            class={cn(
              'ml-auto grid size-ui-sm place-items-center rounded-sm text-fg-muted hover:bg-tint hover:text-fg',
              diagnostics && 'bg-tint text-fg'
            )}
            title="Diagnostics"
            aria-label="Diagnostics"
            aria-pressed={diagnostics}
            onclick={toggleDiagnostics}
          >
            <Bug class="size-5 **:stroke-[1.25]" aria-hidden="true" />
          </button>
        </div>
      </footer>
    </Pane>
    <PaneDivider />
    <Pane
      {...livePane}
      role="region"
      aria-label="Live profile"
      class="grid min-w-0 grid-rows-[auto_minmax(0,1fr)_auto] bg-pane"
    >
      <div class="app-bar px-4">{@render liveControls?.()}</div>
      <PaneGroup direction="vertical" bind:ref={liveColumnEl} class="min-h-0">
        <Pane class="min-h-0" minSize={20}>
          <SplitView
            class="min-h-0"
            panes={{
              image: { horizontal: { min: 30 }, vertical: { min: 15 } },
              settings: { horizontal: { min: 28, default: 32, max: 48 }, vertical: { min: 12 } }
            }}
            persist="live-profile"
            bind:controls={liveControls}
          >
            {#snippet image()}<section
                class="bg-image h-full"
                aria-label="Live view"
                inert={!connected}
              ></section>{/snippet}
            {#snippet settings()}<section
                class="h-full overflow-y-auto"
                aria-label="Light settings"
                inert={!connected}
              ></section>{/snippet}
          </SplitView>
        </Pane>
        <PaneDivider ondblclick={() => streamRef && streamPanel.toggle(streamRef)} />
        <Pane bind:this={streamRef} {...streamPanel} defaultSize={0} collapsible class="min-h-0 bg-pane">
          <div class="h-full" role="tabpanel" aria-label={streamTab.get() === 'power' ? 'Power' : 'Stream'}></div>
        </Pane>
      </PaneGroup>
      <footer aria-label="Live stream">
        <div class="status-bar gap-[0.15rem] pr-[0.85rem] pl-[0.6rem]" role="tablist">
          {@render tab('Power', streamOpen && streamTab.get() === 'power', () => pickStreamTab('power'))}
          <span class="flex-1"></span>
          {@render tab('Stream', streamOpen && streamTab.get() === 'stream', () => pickStreamTab('stream'))}
        </div>
      </footer>
    </Pane>
  </PaneGroup>
</div>

{#snippet tab(label: string, selected: boolean, onclick: () => void)}
  <button
    type="button"
    role="tab"
    aria-selected={selected}
    class={cn(
      'h-ui-xs rounded-sm px-[0.4rem] text-sm text-fg-muted hover:bg-tint hover:text-fg',
      selected && 'bg-tint text-fg'
    )}
    {onclick}>{label}</button
  >
{/snippet}
