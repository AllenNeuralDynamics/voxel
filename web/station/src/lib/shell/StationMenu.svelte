<script lang="ts">
  import { getVoxelStation } from '$lib/context.svelte';
  import {
    type InstrumentInspection,
    type StationDiscovery,
    type StationFeedView,
    type StationInfo
  } from '$lib/core/model';
  import { cn, displayName, errorMessage } from '$lib/core/utils';
  import { DropdownMenu } from '$lib/kit';
  import { Check, ChevronDown, LayoutDashboard, TriangleAlert } from '$lib/kit/icons';
  import { ModeSwitch } from '$lib/kit/themes';

  interface StationDetails {
    discovery: StationDiscovery;
    snapshot: StationFeedView;
  }

  interface Props {
    stationId: string;
    stationName: string;
    selectedInstrumentId: string | null;
    disabled?: boolean;
    /** Whether the menu is open. The logo in the rail opens it too, so the layout can bind it. */
    open?: boolean;
    onselectinstrument: (stationId: string, instrumentId: string) => void;
    onclose: () => void;
    ondashboard: () => void;
  }

  let {
    stationId,
    stationName,
    selectedInstrumentId,
    disabled = false,
    open = $bindable(false),
    onselectinstrument,
    onclose,
    ondashboard
  }: Props = $props();
  const app = getVoxelStation();

  let stations = $state.raw<StationInfo[]>([]);
  let details = $state.raw<Record<string, StationDetails>>({});
  let stationErrors = $state.raw<Record<string, string>>({});
  let loading = $state(false);
  let loadError = $state<string | null>(null);
  let names = $state<HTMLElement | null>(null);

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
    class="flex size-4 shrink-0 items-center justify-center"
    role="img"
    aria-label={open ? 'Open' : 'Closed'}
    title={open ? 'Open' : 'Closed'}
  >
    <span
      class={cn(
        'size-1.5 rounded-full border',
        open ? 'border-success-fg bg-success-fg' : 'border-fg-faint bg-transparent'
      )}
    ></span>
  </span>
{/snippet}

{#snippet instrumentItems(station: StationInfo)}
  {@const instruments = instrumentsFor(station.id)}
  {@const activeInstrument = activeInstrumentFor(station.id)}
  {#each instruments as [name, inspection] (name)}
    {@const active = name === activeInstrument}
    {@const selected = station.id === stationId && name === selectedInstrumentId}
    {@const unavailable = Boolean(activeInstrument) && !active}
    {@const issue = hasIssue(inspection)}
    {#snippet instrumentItem()}
      <DropdownMenu.Item
        disabled={disabled || unavailable}
        class={cn(
          'min-w-0 flex-1 data-highlighted:bg-element-hover',
          selected && 'bg-element-selected data-highlighted:bg-element-selected',
          unavailable && 'text-fg-faint'
        )}
        aria-label={`${displayName(name)}, ${active ? 'open' : 'closed'}${selected ? ', selected' : ''}${issue ? ', configuration issues' : ''}`}
        onclick={() => onselectinstrument(station.id, name)}
      >
        {@render statusDot(active)}
        <span class="min-w-0 flex-1 truncate" title={displayName(name)}>{displayName(name)}</span>
        {#if issue}
          <span class="shrink-0" role="img" aria-label="Configuration issues" title="Configuration issues">
            <TriangleAlert class="size-3.5 text-warning-fg" aria-hidden="true" />
          </span>
        {/if}
      </DropdownMenu.Item>
    {/snippet}
    {#if active && station.id === stationId}
      <div role="none" class="flex items-center gap-1">
        {@render instrumentItem()}
        <DropdownMenu.Item
          variant="destructive"
          class="shrink-0 text-sm"
          aria-label={`Close ${displayName(name)}`}
          onclick={onclose}
        >
          Close
        </DropdownMenu.Item>
      </div>
    {:else}
      {@render instrumentItem()}
    {/if}
  {:else}
    <DropdownMenu.Item disabled>
      {stationErrors[station.id] ? 'Unable to load instruments' : loading ? 'Loading instruments…' : 'No instruments'}
    </DropdownMenu.Item>
  {/each}
{/snippet}

<DropdownMenu.Root bind:open onOpenChange={(next) => next && void load()}>
  <DropdownMenu.Trigger
    {disabled}
    class="group flex min-w-0 cursor-pointer items-center self-stretch text-base focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus disabled:cursor-not-allowed disabled:opacity-40"
    aria-label={selectedInstrumentId
      ? `Station and instrument menu: ${stationName}, ${selectedInstrumentLabel}, ${selectedInstrumentOpen ? 'open' : 'closed'}`
      : `Station and instrument menu: ${stationName}, no instrument selected`}
  >
    <span
      bind:this={names}
      class="ml-2 flex h-ui-sm min-w-0 items-center gap-1.5 rounded-md px-2 transition-colors group-hover:bg-element-hover group-data-[state=open]:bg-element-hover"
    >
      <span class="min-w-0 truncate text-fg-muted" title={`Station: ${stationName}`}>{stationName}</span>
      <span class="shrink-0 text-fg-faint" aria-hidden="true">/</span>
      <span
        class={cn('min-w-0 truncate', selectedInstrumentId ? 'font-medium text-fg' : 'text-fg-muted')}
        title={`Instrument: ${selectedInstrumentLabel}`}>{selectedInstrumentLabel}</span
      >
      <ChevronDown class="size-3.5 shrink-0 text-fg-muted" />
    </span>
  </DropdownMenu.Trigger>

  <!-- A press on the logo toggles the menu itself, so it does not count as a press outside. -->
  <DropdownMenu.Content
    customAnchor={names}
    side="bottom"
    align="start"
    sideOffset={6}
    class="w-72"
    onInteractOutside={(event) => {
      if ((event.target as Element | null)?.closest('[data-opens-station-menu]')) event.preventDefault();
    }}
  >
    {#if showExpandedStations}
      {#each visibleStations as station, index (station.id)}
        {#if index > 0}
          <DropdownMenu.Separator />
        {/if}
        <DropdownMenu.Group>
          <DropdownMenu.GroupHeading class="flex items-center gap-2 text-fg-muted">
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
        <DropdownMenu.GroupHeading class="text-fg-muted">Stations</DropdownMenu.GroupHeading>
        {#each visibleStations as station (station.id)}
          <DropdownMenu.Sub>
            <DropdownMenu.SubTrigger class="data-highlighted:bg-element-active data-[state=open]:bg-element-active">
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
      <DropdownMenu.Item disabled class="text-sm text-danger-fg">Unable to load stations</DropdownMenu.Item>
    {/if}
    <DropdownMenu.Separator />
    <DropdownMenu.Item onclick={ondashboard}>
      <LayoutDashboard class="size-4" aria-hidden="true" />
      Go to dashboard
    </DropdownMenu.Item>
    <DropdownMenu.Separator />
    <ModeSwitch />
  </DropdownMenu.Content>
</DropdownMenu.Root>
