<script lang="ts">
  import { AlertOutline, Check, ChevronsUpDown, Cog, ViewDashboardOutline } from '$lib/icons';
  import { DropdownMenu } from '$lib/kit';
  import {
    errorMessage,
    getVoxelStation,
    type InstrumentInspection,
    type StationDiscovery,
    type StationFeedView,
    type StationInfo
  } from '$lib/model';
  import { cn, displayName } from '$lib/utils';

  interface StationDetails {
    discovery: StationDiscovery;
    snapshot: StationFeedView;
  }

  interface Props {
    stationId: string;
    stationName: string;
    selectedInstrumentId: string | null;
    disabled?: boolean;
    onselectinstrument: (stationId: string, instrumentId: string) => void;
    onclose: () => void;
    onsettings: () => void;
    ondashboard: () => void;
  }

  const {
    stationId,
    stationName,
    selectedInstrumentId,
    disabled = false,
    onselectinstrument,
    onclose,
    onsettings,
    ondashboard
  }: Props = $props();
  const app = getVoxelStation();

  let stations = $state.raw<StationInfo[]>([]);
  let details = $state.raw<Record<string, StationDetails>>({});
  let stationErrors = $state.raw<Record<string, string>>({});
  let loading = $state(false);
  let loadError = $state<string | null>(null);

  const visibleStations = $derived(
    stations.length > 0
      ? [...stations].sort((left, right) => left.name.localeCompare(right.name))
      : [{ id: stationId, name: stationName }]
  );
  const showExpandedStations = $derived(visibleStations.length < 3);
  const selectedInstrumentLabel = $derived(
    selectedInstrumentId ? displayName(selectedInstrumentId) : 'Select instrument…'
  );
  const selectedInstrumentOpen = $derived(Boolean(selectedInstrumentId && app.activeName === selectedInstrumentId));

  function instrumentsFor(targetStationId: string): [string, InstrumentInspection][] {
    const instruments =
      targetStationId === stationId
        ? app.discovery.instruments
        : (details[targetStationId]?.discovery.instruments ?? {});
    return Object.entries(instruments).sort(([left], [right]) => left.localeCompare(right));
  }

  function activeInstrumentFor(targetStationId: string): string | null {
    return targetStationId === stationId
      ? app.activeName
      : (details[targetStationId]?.snapshot.session?.info.instrument_name ?? null);
  }

  function hasIssue(inspection: InstrumentInspection): boolean {
    return inspection.config.status !== 'loaded' || inspection.violations.length > 0;
  }

  async function load(): Promise<void> {
    if (loading) return;
    loading = true;
    loadError = null;
    try {
      stations = await app.client.get<StationInfo[]>('/stations');
      await Promise.all(
        stations
          .filter((station) => station.id !== stationId)
          .map(async (station) => {
            const base = `/stations/${encodeURIComponent(station.id)}`;
            try {
              const [discovery, snapshot] = await Promise.all([
                app.client.get<StationDiscovery>(`${base}/discovery`),
                app.client.get<StationFeedView>(`${base}/snapshot`)
              ]);
              details = { ...details, [station.id]: { discovery, snapshot } };
            } catch (error) {
              stationErrors = { ...stationErrors, [station.id]: errorMessage(error) };
            }
          })
      );
    } catch (error) {
      loadError = errorMessage(error);
    } finally {
      loading = false;
    }
  }
</script>

{#snippet statusDot(open: boolean)}
  <span
    class={cn(
      'size-1.5 shrink-0 rounded-full border',
      open ? 'border-success bg-success' : 'border-fg-faint/60 bg-transparent'
    )}
    role="img"
    aria-label={open ? 'Open' : 'Closed'}
    title={open ? 'Open' : 'Closed'}
  ></span>
{/snippet}

{#snippet instrumentItems(station: StationInfo)}
  {@const instruments = instrumentsFor(station.id)}
  {@const activeInstrument = activeInstrumentFor(station.id)}
  {#each instruments as [name, inspection] (name)}
    {@const active = name === activeInstrument}
    {@const selected = station.id === stationId && name === selectedInstrumentId}
    {@const unavailable = Boolean(activeInstrument) && !active}
    {@const issue = hasIssue(inspection)}
    <DropdownMenu.Item
      disabled={disabled || unavailable}
      class={cn(
        'text-base data-highlighted:bg-element-hover',
        selected && 'bg-element-selected/50 data-highlighted:bg-element-selected',
        unavailable && 'text-fg-faint'
      )}
      aria-label={`${displayName(name)}, ${active ? 'open' : 'closed'}${selected ? ', selected' : ''}${issue ? ', configuration issues' : ''}`}
      onclick={() => onselectinstrument(station.id, name)}
    >
      {@render statusDot(active)}
      <span class="min-w-0 flex-1 truncate" title={displayName(name)}>{displayName(name)}</span>
      {#if issue}
        <span class="shrink-0" role="img" aria-label="Configuration issues" title="Configuration issues">
          <AlertOutline class="size-3.5 text-warning" aria-hidden="true" />
        </span>
      {/if}
    </DropdownMenu.Item>
    {#if active && station.id === stationId}
      <DropdownMenu.Item inset variant="destructive" class="text-sm" onclick={onclose}>
        Close {displayName(name)}
      </DropdownMenu.Item>
    {/if}
  {:else}
    <DropdownMenu.Item disabled class="text-base">
      {stationErrors[station.id] ? 'Unable to load instruments' : loading ? 'Loading instruments…' : 'No instruments'}
    </DropdownMenu.Item>
  {/each}
{/snippet}

<DropdownMenu.Root onOpenChange={(open) => open && void load()}>
  <DropdownMenu.Trigger
    {disabled}
    class="flex w-full cursor-pointer items-center gap-2 rounded-md py-1 pr-0.5 pl-2 text-left transition-colors hover:bg-element-hover disabled:cursor-not-allowed disabled:opacity-40 data-[state=open]:bg-element-hover"
    title="Station and instrument menu"
    aria-label={selectedInstrumentId
      ? `Station and instrument menu: ${selectedInstrumentLabel}, ${selectedInstrumentOpen ? 'open' : 'closed'}`
      : 'Select an instrument'}
  >
    <span class="flex min-w-0 flex-1 flex-col">
      <span
        class={cn('min-w-0 truncate text-lg leading-tight', selectedInstrumentId ? 'text-fg' : 'text-fg-muted')}
        title={selectedInstrumentLabel}
      >
        {selectedInstrumentLabel}
      </span>
      <span class="mt-0.5 w-full truncate text-sm leading-tight text-fg-muted" title={stationName}>{stationName}</span>
    </span>
    <ChevronsUpDown class="size-4 shrink-0 text-fg-muted" />
  </DropdownMenu.Trigger>

  <DropdownMenu.Content side="right" align="start" sideOffset={14} class="w-72">
    {#if showExpandedStations}
      {#each visibleStations as station, index (station.id)}
        {#if index > 0}
          <DropdownMenu.Separator />
        {/if}
        <DropdownMenu.Group>
          <DropdownMenu.GroupHeading class="flex items-center gap-2 text-sm text-fg-muted">
            <span class="min-w-0 flex-1 truncate" title={station.name}>{station.name}</span>
            {#if station.id === stationId}
              <span class="text-xs text-fg-faint">Current</span>
            {/if}
          </DropdownMenu.GroupHeading>
          {@render instrumentItems(station)}
        </DropdownMenu.Group>
      {/each}
    {:else}
      <DropdownMenu.Group>
        <DropdownMenu.GroupHeading class="text-sm text-fg-muted">Stations</DropdownMenu.GroupHeading>
        {#each visibleStations as station (station.id)}
          <DropdownMenu.Sub>
            <DropdownMenu.SubTrigger
              class="text-base data-highlighted:bg-element-active data-[state=open]:bg-element-active"
            >
              <span class="min-w-0 flex-1 truncate" title={station.name}>{station.name}</span>
              {#if station.id === stationId}
                <Check class="size-4 text-fg" aria-label="Current station" />
              {/if}
            </DropdownMenu.SubTrigger>
            <DropdownMenu.SubContent class="w-64">
              {@render instrumentItems(station)}
            </DropdownMenu.SubContent>
          </DropdownMenu.Sub>
        {/each}
      </DropdownMenu.Group>
    {/if}

    {#if loadError}
      <DropdownMenu.Separator />
      <DropdownMenu.Item disabled class="text-sm text-danger">Unable to load stations</DropdownMenu.Item>
    {/if}
    <DropdownMenu.Separator />
    <DropdownMenu.Item class="text-base" onclick={ondashboard}>
      <ViewDashboardOutline class="size-4" aria-hidden="true" />
      Go to dashboard
    </DropdownMenu.Item>
    <DropdownMenu.Item class="text-base" onclick={onsettings}>
      <Cog class="size-4" aria-hidden="true" />
      App settings
    </DropdownMenu.Item>
  </DropdownMenu.Content>
</DropdownMenu.Root>
