<script lang="ts">
  import { onDestroy, onMount } from 'svelte';

  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { DASHBOARD_WINDOW_NAME } from '$lib/app-windows';
  import { Cog, Plus } from '$lib/icons';
  import { DropdownMenu } from '$lib/kit';
  import { dashboardInstrumentPath, newInstrumentPath, settingsPath, stationPath, stationsPath } from '$lib/routes';
  import { cn, displayName, toastError } from '$lib/utils';
  import VoxelLogo from '$lib/VoxelLogo.svelte';

  import { DashboardState, setDashboardState } from './state.svelte';

  const { children } = $props();
  const dashboard = new DashboardState();
  setDashboardState(dashboard);
  const selectedStationId = $derived(page.params.stationId ?? null);
  const requestedInstrument = $derived(page.url.searchParams.get('instrument'));
  const requestedTemplate = $derived(page.url.searchParams.get('template'));
  const settingsSelected = $derived(page.route.id?.endsWith('/settings') ?? false);

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
</script>

<svelte:head>
  <title>Voxel Dashboard</title>
</svelte:head>

<div class="h-screen bg-canvas text-fg">
  <main class="h-full min-h-0 overflow-hidden">
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
          <a
            href={settingsPath()}
            class={cn(
              'flex size-ui-lg shrink-0 items-center justify-center rounded-md text-fg-muted transition-colors hover:bg-element-hover hover:text-fg',
              settingsSelected && 'bg-element-selected text-fg'
            )}
            title="Settings"
            aria-label="Settings"
          >
            <Cog width="18" height="18" />
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
            <div class="space-y-3">
              {#each dashboard.stations as station (station.id)}
                {@const discovery = dashboard.discoveries.get(station.id)}
                {@const stationActiveInstrument = activeInstrument(station.id)}
                {@const isSelectedStation = selectedStationId === station.id}
                {@const stationUnavailable = dashboard.stationErrors.has(station.id)}
                <section class="space-y-0.5">
                  <div class="flex min-h-ui-md items-center gap-2 px-2">
                    <a
                      href={stationPath(station.id)}
                      class={cn(
                        'min-w-0 flex-1 truncate text-sm font-medium tracking-wide uppercase transition-colors',
                        stationUnavailable ? 'text-fg-faint' : 'text-fg-muted hover:text-fg'
                      )}
                      title={station.name}
                    >
                      {station.name}
                    </a>
                    <DropdownMenu.Root>
                      <DropdownMenu.Trigger
                        disabled={stationUnavailable || !discovery || Object.keys(discovery.templates).length === 0}
                        class={cn(
                          'flex size-ui-xs shrink-0 items-center justify-center rounded text-fg-muted transition-colors hover:bg-element-hover hover:text-fg disabled:cursor-not-allowed disabled:opacity-40',
                          isSelectedStation && requestedTemplate && 'bg-element-selected text-fg'
                        )}
                        title={stationUnavailable
                          ? 'Station unavailable'
                          : discovery && Object.keys(discovery.templates).length === 0
                            ? 'No instrument templates available'
                            : `New instrument on ${station.name}`}
                        aria-label={`New instrument on ${station.name}`}
                      >
                        <Plus width="14" height="14" />
                      </DropdownMenu.Trigger>
                      {#if discovery}
                        <DropdownMenu.Content align="end" class="w-64">
                          {#each Object.keys(discovery.templates).sort( (left, right) => left.localeCompare(right) ) as template (template)}
                            <DropdownMenu.Item onclick={() => goto(newInstrumentPath(station.id, template))}>
                              <span class="truncate text-base">{displayName(template)}</span>
                            </DropdownMenu.Item>
                          {/each}
                        </DropdownMenu.Content>
                      {/if}
                    </DropdownMenu.Root>
                  </div>

                  {#if stationUnavailable}
                    <p class="px-2 py-1.5 text-sm text-danger">Station unavailable</p>
                  {:else if discovery}
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
                      </a>
                    {/each}
                  {:else}
                    <p class="px-2 py-1.5 text-sm text-fg-muted">Loading instruments…</p>
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
  </main>
</div>
