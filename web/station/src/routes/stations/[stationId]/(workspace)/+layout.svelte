<script lang="ts">
  import { onDestroy } from 'svelte';

  import { afterNavigate, goto } from '$app/navigation';
  import { page } from '$app/state';
  import { getInstrumentSelection, getVoxelStation, provideAppBar } from '$lib/context.svelte';
  import type { ConnectionState } from '$lib/core/model/client.svelte';
  import { Linger } from '$lib/core/utils/linger.svelte';
  import AppBar from '$lib/shell/AppBar.svelte';
  import { LiveDock } from '$lib/shell/live-dock.svelte';
  import LiveProfile from '$lib/shell/LiveProfile.svelte';
  import LogoMenu from '$lib/shell/LogoMenu.svelte';
  import ProfileSelect from '$lib/shell/ProfileSelect.svelte';
  import * as Rail from '$lib/shell/rail';
  import StationMenu from '$lib/shell/StationMenu.svelte';
  import { cn } from '@voxel/kit/cn';
  import { displayName } from '@voxel/kit/format';
  import {
    Activity,
    ChartNoAxesColumn,
    Cpu,
    FileCog,
    History,
    Loader,
    Maximize2,
    Minimize2,
    Play,
    Radio,
    RadioOff,
    Route,
    Video,
    X
  } from '@voxel/kit/icons';
  import { AutoSplit, createPaneSize, Pane, PaneDivider, PaneGroup } from '@voxel/kit/pane';

  import type { LayoutProps } from './$types';

  let { children, params }: LayoutProps = $props();

  const station = getVoxelStation();
  const selection = getInstrumentSelection();
  const appBar = provideAppBar();
  const live = new LiveDock(() => params.stationId);
  onDestroy(() => live.dispose());

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

  // Diagnostics, under the page: the log, with the issues beside or under it while there are any. The bar below it
  // shows what runs now (else the newest log line) and the number of issues, and a click on it opens or closes
  // Diagnostics, which starts closed and opens at its saved height. It can fill the page; closing it, or going to
  // another page, puts the page back.
  let pageColumnEl = $state<HTMLElement | null>(null);
  let pageRef = $state<Pane | undefined>(undefined);
  let diagnosticsRef = $state<Pane | undefined>(undefined);
  // The page keeps at least half the column while the panel is dragged. A pull far past that collapses it, as
  // filling the page does.
  const pageSize = createPaneSize(() => pageColumnEl, {
    collapsed: 0,
    get min() {
      const rem = parseFloat(getComputedStyle(document.documentElement).fontSize);
      return (pageColumnEl?.getBoundingClientRect().height ?? 0) / rem / 2;
    },
    fallback: { collapsed: 0, min: 50 }
  });
  const diagnosticsSize = createPaneSize(() => pageColumnEl, {
    collapsed: 0,
    min: 12,
    default: 17,
    fallback: { collapsed: 0, min: 15, default: 30 },
    persist: 'page-footer'
  });
  const diagnosticsOpen = $derived(diagnosticsRef ? !diagnosticsRef.isCollapsed() : false);
  const diagnosticsFull = $derived(pageRef ? pageRef.isCollapsed() : false);
  let openBeforeFull = false;

  function toggleDiagnostics(): void {
    if (!diagnosticsRef) return;
    if (diagnosticsFull) pageRef?.expand();
    diagnosticsSize.toggle(diagnosticsRef);
  }

  function toggleDiagnosticsFull(): void {
    if (!pageRef || !diagnosticsRef) return;
    if (diagnosticsFull) {
      pageRef.expand();
      if (!openBeforeFull) diagnosticsRef.collapse();
      return;
    }
    openBeforeFull = diagnosticsOpen;
    if (!diagnosticsOpen) diagnosticsSize.toggle(diagnosticsRef);
    pageRef.collapse();
  }

  afterNavigate(() => {
    if (diagnosticsFull) toggleDiagnosticsFull();
  });

  const alerts = $derived(station.instrument?.alerts ?? []);
  const worstAlertLevel = $derived(alerts.some((alert) => alert.level === 'error') ? 'error' : 'warning');
  // Held 1 s after it ends, so a quick operation does not flash in the bar.
  const runningOperation = new Linger(() => station.instrument?.operation ?? null, 1000);
  // The bar's line skips debug lines, which would flicker past while they are on.
  const newestLogLine = $derived(station.log.findLast((line) => line.level >= 20) ?? null);
  // A log message's color by its level: debug faint, info plain, warning amber, error red.
  const logLineColor = (level: number): string =>
    level >= 40 ? 'text-danger-fg' : level >= 30 ? 'text-warning-fg' : level >= 20 ? 'text-fg' : 'text-fg-faint';
  const logTime = (iso: string): string => new Date(iso).toLocaleTimeString([], { hour12: false });
</script>

<div class="flex h-screen w-screen overflow-hidden text-fg">
  <div class="grid shrink-0 grid-rows-[auto_minmax(0,1fr)_auto]">
    <div class="app-bar w-rail justify-center border-r px-1.5">
      <LogoMenu
        show={live.docked ? undefined : { label: 'Show live profile', icon: Video, onclick: () => live.show() }}
        settings={{ onclick: () => goto(`${home}/settings`) }}
        docked={live.docked}
        onDock={(docked) => (docked ? live.dock() : live.undock())}
      />
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
    <Pane {...pagePane} id="page" order={1} class="grid min-w-0 grid-rows-[auto_minmax(0,1fr)_auto]">
      <div class="app-bar min-w-0 px-4">
        <AppBar bar={appBar}>
          {#snippet start()}<StationMenu {selection} />{/snippet}
          {#snippet end()}
            <!-- The live profile's own controls, while it is in another window. -->
            {#if !live.docked}<ProfileSelect />{/if}
          {/snippet}
        </AppBar>
      </div>
      <PaneGroup direction="vertical" bind:ref={pageColumnEl} class="min-h-0">
        <Pane bind:this={pageRef} {...pageSize} collapsible class="min-h-0">
          <main class="flex h-full min-h-0 min-w-0 flex-col overflow-hidden bg-pane" inert={!connected || notOpen}>
            {@render children()}
          </main>
        </Pane>
        <PaneDivider ondblclick={() => diagnosticsRef && diagnosticsSize.toggle(diagnosticsRef)} />
        <Pane bind:this={diagnosticsRef} {...diagnosticsSize} defaultSize={0} collapsible class="min-h-0 bg-pane">
          <div class="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)]">
            <div class="flex h-ui-md items-center gap-1 border-b border-line-faint pr-2 pl-4">
              <h2 class="flex-1 text-sm font-medium text-fg-muted">Diagnostics</h2>
              <button
                type="button"
                class={cn(
                  'grid size-ui-xs place-items-center rounded-sm text-fg-muted hover:bg-tint hover:text-fg',
                  diagnosticsFull && 'bg-tint text-fg'
                )}
                title={diagnosticsFull ? 'Back to the page' : 'Fill the page'}
                aria-label={diagnosticsFull ? 'Back to the page' : 'Fill the page'}
                aria-pressed={diagnosticsFull}
                onclick={toggleDiagnosticsFull}
              >
                {#if diagnosticsFull}
                  <Minimize2 class="size-3" aria-hidden="true" />
                {:else}
                  <Maximize2 class="size-3" aria-hidden="true" />
                {/if}
              </button>
              <button
                type="button"
                class="grid size-ui-xs place-items-center rounded-sm text-fg-muted hover:bg-tint hover:text-fg"
                title="Close"
                aria-label="Close"
                onclick={toggleDiagnostics}
              >
                <X class="size-4" aria-hidden="true" />
              </button>
            </div>
            {#if alerts.length > 0}
              <AutoSplit
                persist="dock"
                panes={{
                  log: { horizontal: { min: 40 }, vertical: { min: 6 } },
                  issues: { horizontal: { min: 16, default: 20, max: 32 }, vertical: { min: 3, default: 6 } }
                }}
              >
                {#snippet issues()}
                  <section class="flex h-full min-h-0 flex-col" aria-label="Issues">
                    <ul class="min-h-0 flex-1 overflow-y-auto p-2">
                      {#each alerts as alert (`${alert.code}:${alert.loc.join('.')}`)}
                        <li
                          class="grid grid-cols-[0.5rem_minmax(0,1fr)] items-start gap-2 rounded-sm px-2 py-1 text-sm hover:bg-tint"
                        >
                          <span
                            class={cn(
                              'mt-[0.45rem] size-2 rounded-full',
                              alert.level === 'error' ? 'bg-danger-fg' : 'bg-warning-fg'
                            )}
                            aria-label={alert.level === 'error' ? 'Error' : 'Warning'}
                            role="img"
                          ></span>
                          <span class="min-w-0">
                            {alert.msg}
                            {#if alert.loc.length > 0}<span class="text-fg-faint"> · {alert.loc.join('.')}</span>{/if}
                          </span>
                        </li>
                      {/each}
                    </ul>
                  </section>
                {/snippet}
                {#snippet log()}{@render logLines()}{/snippet}
              </AutoSplit>
            {:else}
              {@render logLines()}
            {/if}
          </div>
        </Pane>
      </PaneGroup>
      <footer>
        <!-- The whole bar opens and closes Diagnostics: what runs now, else the newest log line, then the issues. -->
        <button
          type="button"
          class={cn(
            'status-bar w-full gap-2 px-4 text-left text-sm whitespace-nowrap hover:bg-tint',
            diagnosticsOpen && 'bg-tint'
          )}
          aria-expanded={diagnosticsOpen}
          onclick={toggleDiagnostics}
        >
          <span class="flex min-w-0 flex-1 items-center gap-3">
            {#if runningOperation.current}
              <Loader class="size-3.5 shrink-0 animate-spin text-accent-fg" aria-hidden="true" />
              <span class="truncate text-fg">{displayName(runningOperation.current)}…</span>
            {:else if newestLogLine}
              <time class="w-[5rem] shrink-0 font-mono text-fg-faint" datetime={newestLogLine.emitted_at}
                >{logTime(newestLogLine.emitted_at)}</time
              >
              <span class="truncate text-fg-faint">{newestLogLine.message}</span>
            {/if}
          </span>
          {#if station.instrument}
            <span
              class={cn(
                'shrink-0',
                alerts.length === 0
                  ? 'text-fg-faint'
                  : ['font-medium', worstAlertLevel === 'error' ? 'text-danger-fg' : 'text-warning-fg']
              )}
            >
              {alerts.length}
              {alerts.length === 1 ? 'issue' : 'issues'}
            </span>
          {/if}
        </button>
      </footer>
    </Pane>
    {#if live.docked}
      <PaneDivider />
      <Pane {...livePane} id="live" order={2} role="region" aria-label="Live profile" class="min-w-0">
        <LiveProfile {connected}>
          {#snippet start()}
            <h2 class="flex min-w-0 items-center gap-1.5 pl-4 font-medium whitespace-nowrap">
              {#if openName && openName !== selection.selected}
                <button
                  type="button"
                  class="truncate font-normal text-fg-muted hover:text-fg hover:underline"
                  onclick={() => openName && selection.select(openName)}>{displayName(openName)}</button
                >
                <span class="text-fg-faint">/</span>
              {/if}
              Live
            </h2>
          {/snippet}
        </LiveProfile>
      </Pane>
    {/if}
  </PaneGroup>
</div>

{#snippet logLines()}
  <section class="flex h-full min-h-0 flex-col" aria-label="Log">
    <!-- Reversed, so the newest line stays in view at the bottom while lines come in. -->
    <ol class="flex min-h-0 flex-1 flex-col-reverse overflow-y-auto py-2 font-mono text-sm">
      {#each station.log.toReversed() as line (line.seq)}
        <!-- As the status bar: the time, then the message; the logger last. -->
        <li class="grid grid-cols-[5rem_minmax(0,1fr)_auto] gap-3 px-4 hover:bg-tint">
          <time class="text-fg-faint" datetime={line.emitted_at}>{logTime(line.emitted_at)}</time>
          <span class={cn('truncate', logLineColor(line.level))} title={line.message}>{line.message}</span>
          <span class="max-w-48 truncate text-fg-faint">{line.logger}</span>
        </li>
      {/each}
    </ol>
  </section>
{/snippet}
