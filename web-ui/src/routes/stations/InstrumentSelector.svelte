<script lang="ts">
  import { onMount } from 'svelte';
  import { SvelteMap } from 'svelte/reactivity';

  import { Check, ChevronsUpDown } from '$lib/icons';
  import { DropdownMenu, Spinner } from '$lib/kit';
  import {
    errorMessage,
    getVoxelStation,
    type InstrumentInspection,
    type StationDiscovery,
    type StationFeedView,
    type StationInfo
  } from '$lib/model';
  import { cn, displayName } from '$lib/utils';

  interface Props {
    stationId: string;
    instrumentId: string;
    anchor?: HTMLElement | null;
    disabled?: boolean;
    onselect: (stationId: string, instrumentId: string) => void;
  }

  const { stationId, instrumentId, anchor = null, disabled = false, onselect }: Props = $props();
  const app = getVoxelStation();
  const discoveries = new SvelteMap<string, StationDiscovery>();
  const snapshots = new SvelteMap<string, StationFeedView>();
  const errors = new SvelteMap<string, string>();
  let stations = $state.raw<StationInfo[]>([]);
  let loading = $state(false);
  let loadError = $state<string | null>(null);

  const sortedStations = $derived([...stations].sort((left, right) => left.name.localeCompare(right.name)));

  function hasIssue(inspection: InstrumentInspection): boolean {
    return inspection.config.status !== 'loaded' || inspection.violations.length > 0;
  }

  function activeInstrument(targetStationId: string): string | null {
    return targetStationId === stationId
      ? app.activeName
      : (snapshots.get(targetStationId)?.session?.info.instrument_name ?? null);
  }

  async function load(): Promise<void> {
    if (loading) return;
    loading = true;
    loadError = null;
    try {
      stations = await app.client.get<StationInfo[]>('/stations');
      discoveries.set(stationId, app.discovery);
      await Promise.allSettled(
        stations
          .filter(({ id }) => id !== stationId)
          .map(async ({ id }) => {
            errors.delete(id);
            const base = `/stations/${encodeURIComponent(id)}`;
            try {
              const [discovery, snapshot] = await Promise.all([
                app.client.get<StationDiscovery>(`${base}/discovery`),
                app.client.get<StationFeedView>(`${base}/snapshot`)
              ]);
              discoveries.set(id, discovery);
              snapshots.set(id, snapshot);
            } catch (error) {
              discoveries.delete(id);
              snapshots.delete(id);
              errors.set(id, errorMessage(error));
            }
          })
      );
    } catch (error) {
      loadError = errorMessage(error);
    } finally {
      loading = false;
    }
  }

  onMount(() => void load());
</script>

<DropdownMenu.Root onOpenChange={(open) => open && void load()}>
  <DropdownMenu.Trigger
    {disabled}
    class="flex w-7 shrink-0 cursor-pointer items-center justify-center text-fg-muted transition-colors hover:bg-element-hover/80 hover:text-fg disabled:cursor-not-allowed disabled:opacity-40"
    title="Choose instrument"
    aria-label="Choose instrument"
  >
    {#if loading && stations.length === 0}
      <Spinner class="size-3.5" />
    {:else}
      <ChevronsUpDown width="14" height="14" />
    {/if}
  </DropdownMenu.Trigger>
  <DropdownMenu.Content customAnchor={anchor} align="start" class="w-(--bits-floating-anchor-width)">
    {#each sortedStations as station, stationIndex (station.id)}
      {#if stationIndex > 0}
        <DropdownMenu.Separator />
      {/if}
      <DropdownMenu.Group>
        {@const discovery = discoveries.get(station.id)}
        <DropdownMenu.GroupHeading class="text-sm font-medium text-fg-muted">{station.name}</DropdownMenu.GroupHeading>
        {#if discovery}
          {#each Object.entries(discovery.instruments).sort( ([left], [right]) => left.localeCompare(right) ) as [name, inspection] (name)}
            {@const selected = station.id === stationId && name === instrumentId}
            {@const active = activeInstrument(station.id) === name}
            {@const invalid = hasIssue(inspection)}
            <DropdownMenu.Item class="text-base" onclick={() => onselect(station.id, name)}>
              <span
                class={cn(
                  'size-1.5 shrink-0 rounded-full',
                  invalid ? 'bg-danger' : active ? 'bg-success' : 'bg-fg-faint'
                )}
                aria-hidden="true"
              ></span>
              <span class="min-w-0 flex-1 truncate" title={displayName(name)}>{displayName(name)}</span>
              {#if selected}
                <Check class="size-4 text-fg" aria-label="Selected" />
              {/if}
            </DropdownMenu.Item>
          {:else}
            <DropdownMenu.Item disabled class="text-base">No instruments</DropdownMenu.Item>
          {/each}
        {:else if errors.has(station.id)}
          <DropdownMenu.Item disabled class="text-base text-danger">Station unavailable</DropdownMenu.Item>
        {:else}
          <DropdownMenu.Item disabled class="text-base">Loading instruments…</DropdownMenu.Item>
        {/if}
      </DropdownMenu.Group>
    {:else}
      <DropdownMenu.Item disabled class={cn('text-base', loadError && 'text-danger')}>
        {loading ? 'Loading stations…' : loadError ? 'Unable to load stations' : 'No stations'}
      </DropdownMenu.Item>
    {/each}
  </DropdownMenu.Content>
</DropdownMenu.Root>
