<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { SvelteSet } from 'svelte/reactivity';

  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { DASHBOARD_WINDOW_NAME } from '$lib/app-windows';
  import { ChevronRight, Microscope, Plus, Power } from '$lib/icons';
  import { DropdownMenu } from '$lib/kit';
  import { dashboardInstrumentPath, newInstrumentPath, stationPath, stationsPath } from '$lib/routes';
  import { cn, displayName, toastError } from '$lib/utils';
  import VoxelLogo from '$lib/VoxelLogo.svelte';

  import { DashboardState, setDashboardState } from './state.svelte';

  const { children } = $props();
  const dashboard = new DashboardState();
  setDashboardState(dashboard);
  const expanded = new SvelteSet<string>();
  const knownStations = new SvelteSet<string>();
  const selectedStationId = $derived(page.params.stationId ?? null);
  const requestedInstrument = $derived(page.url.searchParams.get('instrument'));
  const requestedTemplate = $derived(page.url.searchParams.get('template'));

  onMount(() => {
    window.name = DASHBOARD_WINDOW_NAME;
    toastError(dashboard.initialize());
    const refreshVisibleDashboard = () => {
      if (document.visibilityState === 'visible') void dashboard.refresh();
    };
    window.addEventListener('focus', refreshVisibleDashboard);
    document.addEventListener('visibilitychange', refreshVisibleDashboard);
    return () => {
      window.removeEventListener('focus', refreshVisibleDashboard);
      document.removeEventListener('visibilitychange', refreshVisibleDashboard);
    };
  });
  onDestroy(() => dashboard.dispose());

  $effect(() => {
    for (const { id } of dashboard.stations) {
      if (knownStations.has(id)) continue;
      knownStations.add(id);
      expanded.add(id);
    }
  });

  function activeInstrument(stationId: string): string | null {
    return dashboard.snapshots.get(stationId)?.session?.info.instrument_name ?? null;
  }

  function selectedInstrument(stationId: string): string | null {
    if (stationId !== selectedStationId || requestedTemplate) return null;
    const instruments = dashboard.discoveries.get(stationId)?.instruments;
    if (!instruments) return null;
    if (requestedInstrument && requestedInstrument in instruments) return requestedInstrument;
    const active = activeInstrument(stationId);
    if (active && active in instruments) return active;
    return Object.keys(instruments).sort((left, right) => left.localeCompare(right))[0] ?? null;
  }

  function toggleStation(stationId: string): void {
    if (expanded.has(stationId)) expanded.delete(stationId);
    else expanded.add(stationId);
  }
</script>

<div class="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)] lg:grid-cols-[24rem_minmax(0,1fr)] lg:grid-rows-1">
  <aside
    class="max-h-80 min-h-0 overflow-y-auto border-b border-border bg-surface lg:max-h-none lg:border-r lg:border-b-0"
  >
    <div class="flex h-14 items-center border-b border-border px-3">
      <a
        href={stationsPath()}
        class="flex h-ui-lg flex-1 items-center gap-2 rounded-md px-2 transition-colors hover:bg-element-hover"
        aria-label="Voxel stations"
      >
        <VoxelLogo class="size-7 shrink-0" />
        <span class="text-2xl font-normal tracking-wide uppercase">Voxel</span>
      </a>
    </div>

    <nav class="p-2" aria-label="Stations and instruments">
      {#if dashboard.loading && dashboard.stations.length === 0}
        <p class="px-2 py-3 text-fg-muted">Loading stations…</p>
      {:else if dashboard.error && dashboard.stations.length === 0}
        <p class="px-2 py-3 text-danger">{dashboard.error}</p>
      {:else if dashboard.stations.length === 0}
        <p class="px-2 py-3 text-fg-muted">No stations are available.</p>
      {:else}
        <div class="space-y-1">
          {#each dashboard.stations as station (station.id)}
            {@const discovery = dashboard.discoveries.get(station.id)}
            {@const stationActiveInstrument = activeInstrument(station.id)}
            {@const isSelectedStation = selectedStationId === station.id}
            <section>
              <div
                class={cn(
                  'flex min-h-ui-lg items-center rounded-md transition-colors',
                  isSelectedStation
                    ? 'bg-element-selected text-fg'
                    : 'text-fg-muted hover:bg-element-hover hover:text-fg'
                )}
              >
                <a href={stationPath(station.id)} class="flex min-w-0 flex-1 items-center gap-2 px-2 py-2">
                  <Microscope width="16" height="16" class="shrink-0" />
                  <span class="min-w-0 flex-1 truncate font-medium" title={station.name}>{station.name}</span>
                  {#if stationActiveInstrument}
                    <span class="size-1.5 shrink-0 rounded-full bg-success" title="Instrument active"></span>
                  {/if}
                </a>
                <button
                  type="button"
                  class="mr-1 ml-auto flex size-ui-md shrink-0 items-center justify-center rounded text-fg-muted hover:bg-element-hover hover:text-fg"
                  aria-label={`${expanded.has(station.id) ? 'Collapse' : 'Expand'} ${station.name}`}
                  aria-expanded={expanded.has(station.id)}
                  onclick={() => toggleStation(station.id)}
                >
                  <ChevronRight
                    width="16"
                    height="16"
                    class={cn('transition-transform', expanded.has(station.id) && 'rotate-90')}
                  />
                </button>
              </div>

              {#if expanded.has(station.id)}
                <div class="mt-1 ml-5 space-y-0.5 border-l border-border pl-2">
                  {#if discovery}
                    {#each Object.entries(discovery.instruments).sort( ([left], [right]) => left.localeCompare(right) ) as [name, inspection] (name)}
                      {@const active = stationActiveInstrument === name}
                      {@const invalid = inspection.config.status !== 'loaded' || inspection.violations.length > 0}
                      <a
                        href={dashboardInstrumentPath(station.id, name)}
                        class={cn(
                          'flex min-h-ui-md items-center gap-2 rounded-md px-2 py-1.5 transition-colors',
                          selectedInstrument(station.id) === name
                            ? 'bg-element-selected text-fg'
                            : 'text-fg-muted hover:bg-element-hover hover:text-fg'
                        )}
                      >
                        <span
                          class={cn(
                            'size-1.5 shrink-0 rounded-full',
                            invalid ? 'bg-danger' : active ? 'bg-success' : 'bg-fg-faint'
                          )}
                        ></span>
                        <span class="min-w-0 flex-1 truncate" title={displayName(name)}>{displayName(name)}</span>
                        {#if active}
                          <Power width="13" height="13" class="shrink-0 text-success" aria-label="Active" />
                        {/if}
                      </a>
                    {/each}

                    <DropdownMenu.Root>
                      <DropdownMenu.Trigger
                        disabled={Object.keys(discovery.templates).length === 0}
                        class={cn(
                          'flex min-h-ui-md w-full items-center gap-2 rounded-md px-2 py-1.5 text-fg-muted transition-colors hover:bg-element-hover hover:text-fg disabled:cursor-not-allowed disabled:opacity-50',
                          isSelectedStation && requestedTemplate && 'bg-element-selected text-fg'
                        )}
                      >
                        <Plus width="14" height="14" class="shrink-0" />
                        <span>New instrument</span>
                      </DropdownMenu.Trigger>
                      <DropdownMenu.Content align="start" class="w-64">
                        {#each Object.keys(discovery.templates).sort( (left, right) => left.localeCompare(right) ) as template (template)}
                          <DropdownMenu.Item onclick={() => goto(newInstrumentPath(station.id, template))}>
                            <span class="truncate text-base">{displayName(template)}</span>
                          </DropdownMenu.Item>
                        {/each}
                      </DropdownMenu.Content>
                    </DropdownMenu.Root>
                  {:else if dashboard.stationErrors.has(station.id)}
                    <p class="px-2 py-2 text-sm text-danger">Station unavailable</p>
                  {:else}
                    <p class="px-2 py-2 text-sm text-fg-muted">Loading instruments…</p>
                  {/if}
                </div>
              {/if}
            </section>
          {/each}
        </div>
      {/if}
    </nav>
  </aside>

  <section class="min-h-0 min-w-0 bg-canvas">
    {@render children()}
  </section>
</div>
