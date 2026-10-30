<script lang="ts">
  import { resolve } from '$app/paths';
  import { reportFailure } from '$lib/core/failures';
  import type { Instrument } from '$lib/core/model';
  import { prefs } from '$lib/core/prefs';
  import { cn, displayName } from '$lib/core/utils';
  import { delayedTrue } from '$lib/core/utils/delayed-true.svelte';
  import { MultiSelect } from '$lib/core/utils/multiselect.svelte';
  import { ChannelCard, LiveFilterWheels, LiveROI, LiveRoutes } from '$lib/features/live';
  import ChipRow from '$lib/features/live/ChipRow.svelte';
  import { Button, Section, Select } from '$lib/kit';
  import { ArrowRight, Blend, ChartSpline, Loader } from '$lib/kit/icons';

  import RunButton from './RunButton.svelte';

  /** The open instrument. The layout shows this pane only while one is open. */
  let { instrument }: { instrument: Instrument } = $props();

  const rows = $derived(prefs.channelCards.get());
  // The channels that preview runs. Saving a pick restarts a running preview with them.
  const previewPick = new MultiSelect<string>({
    keys: () => instrument.activeChannels.map((channel) => channel.id),
    saved: () => instrument.previewChannels,
    save: (ids) => instrument.setPreviewChannels(ids),
    disabled: () => instrument.busy,
    mode: 'select'
  });
  // A quick save ends before the spinner shows, so it does not flicker.
  const pickPending = delayedTrue(() => previewPick.pending, 200);

  // The Light path rows. Each chip component says when Restore can move its hardware back.
  let wheels = $state<LiveFilterWheels>();
  let routes = $state<LiveRoutes>();
  let restoringFilters = $state(false);
  const hasWheels = $derived(instrument.activeChannels.some((channel) => channel.filters.some(({ filter }) => filter)));
  const hasRoutes = $derived(instrument.routingDimensions.size > 0);

  // 1 button for each row that the channel cards can hide. A button shows only when a card has that row.
  const rowToggles = $derived([
    { row: 'plots', label: 'Power plots', icon: ChartSpline, available: true },
    { row: 'filters', label: 'Filters', icon: Blend, available: hasWheels }
  ] as const);

  async function restoreFilters(): Promise<void> {
    restoringFilters = true;
    try {
      await wheels?.restore();
    } finally {
      restoringFilters = false;
    }
  }

  const profileId = $derived(instrument.activeProfileId ?? '');
  const generators = $derived(Object.entries(instrument.state.imaging.profiles[profileId]?.sync ?? {}));
  const numberFormat = new Intl.NumberFormat(undefined, { maximumSignificantDigits: 6 });
</script>

<div class="app-bar gap-2 px-4">
  <Select
    size="md"
    class="flex-1"
    prefix="Profile"
    aria-label="Active profile"
    title={instrument.busy ? 'Locked while an acquisition runs' : undefined}
    value={instrument.activeProfileId}
    options={Object.keys(instrument.imaging.profiles)}
    formatLabel={(id) => instrument.imaging.profiles[id]?.label || displayName(id)}
    onChange={(id) => instrument.setActiveProfile(id)}
    disabled={instrument.busy}
  >
    {#snippet trailing(id)}
      {#if instrument.plan.some((task) => task.profiles.includes(id))}
        <span
          class="size-1.5 rounded-full bg-fg-muted"
          role="img"
          aria-label="Used by planned tasks"
          title="Used by planned tasks"
        ></span>
      {/if}
    {/snippet}
  </Select>
  <RunButton class="ml-auto" />
</div>
<div class="flex min-h-0 flex-1 scrollbar-gutter-stable flex-col gap-4 overflow-y-auto px-4 py-2">
  <Section class="mb-auto">
    {#snippet heading()}
      <span class="flex min-w-0 items-center gap-1">
        Channels
        {#if previewPick.state === 'all'}
          <span class="border border-transparent px-1 text-sm text-fg-muted tabular-nums" title="All channels preview"
            >{previewPick.count} of {instrument.activeChannels.length}</span
          >
        {:else}
          <Button
            variant="quiet"
            size="xs"
            class="tabular-nums"
            disabled={previewPick.disabled}
            title="Preview all channels"
            onclick={() => previewPick.setAll(true)}>{previewPick.count} of {instrument.activeChannels.length}</Button
          >
        {/if}
        {#if pickPending.current}
          <span role="status" aria-label="Updating preview channels">
            <Loader class="size-3 animate-spin text-fg-muted" />
          </span>
        {/if}
      </span>
    {/snippet}
    {#snippet trailing()}
      <div class="flex items-center gap-0.5">
        {#each rowToggles as toggle (toggle.row)}
          {#if toggle.available}
            {@const shown = rows[toggle.row]}
            <button
              type="button"
              aria-pressed={shown}
              aria-label={toggle.label}
              title={`${shown ? 'Hide' : 'Show'} ${toggle.label.toLowerCase()}`}
              class={cn(
                'flex size-5 items-center justify-center rounded-sm transition-colors hover:bg-element-hover focus-visible:outline-2 focus-visible:outline-focus',
                shown ? 'text-accent-fg' : 'text-fg-faint hover:text-fg'
              )}
              onclick={() => prefs.channelCards.set({ ...rows, [toggle.row]: !shown })}
            >
              <toggle.icon class="size-3" />
            </button>
          {/if}
        {/each}
      </div>
    {/snippet}
    <div class="grid grid-cols-1 gap-3">
      {#each instrument.activeChannels as channel (channel.id)}
        <ChannelCard {channel} {instrument} pick={previewPick} {rows} />
      {/each}
      <LiveROI {instrument} />
    </div>
  </Section>
  {#if hasWheels || hasRoutes}
    <Section heading="Light path">
      <div class="flex min-w-0 flex-col gap-3 frame-raised p-2.5">
        {#if hasWheels}
          <ChipRow
            label="Filters"
            restorable={wheels?.restorable() ?? false}
            disabled={instrument.busy || restoringFilters}
            restoreTitle="Move the wheels to the filters the profile uses"
            restoreLabel="Restore the filters"
            onRestore={() => reportFailure(restoreFilters())}
          >
            <LiveFilterWheels bind:this={wheels} {instrument} />
          </ChipRow>
        {/if}
        {#if hasRoutes}
          <ChipRow
            label="Routes"
            restorable={routes?.restorable() ?? false}
            disabled={instrument.busy || instrument.edits.pending}
            restoreTitle="Move to the routes the rules pick"
            restoreLabel="Restore the routes"
            onRestore={() => routes?.restore()}
          >
            <LiveRoutes bind:this={routes} {instrument} />
          </ChipRow>
        {/if}
      </div>
    </Section>
  {/if}
  <Section>
    {#snippet heading()}
      Synchronization <span class="text-fg-faint tabular-nums">{generators.length}</span>
    {/snippet}
    <div class="grid grid-cols-1 gap-2">
      {#each generators as [generatorId, signals] (generatorId)}
        {@const outputs = Object.keys(signals.waveforms).length}
        <a
          href={resolve('/stations/[stationId]/instruments/[instrumentId]/profiles/[profileId]/sync/[generatorId]', {
            stationId: instrument.stationId,
            instrumentId: instrument.id,
            profileId,
            generatorId
          })}
          class="group flex min-w-0 items-center gap-3 frame-raised-link px-2.5 py-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        >
          <span class="min-w-0 flex-1 truncate text-base text-fg">{displayName(generatorId)}</span>
          <span class="shrink-0 text-sm text-fg-muted tabular-nums"
            >{outputs} {outputs === 1 ? 'output' : 'outputs'}</span
          >
          <span class="shrink-0 text-sm text-fg tabular-nums" title="Active duration">
            {numberFormat.format(signals.duration * 1000)} <span class="text-fg-muted">ms</span>
          </span>
          <ArrowRight class="size-3.5 shrink-0 text-fg-faint group-hover:text-fg" aria-hidden="true" />
        </a>
      {:else}
        <p class="frame-placeholder p-4 text-sm text-fg-muted">No synchronization configured.</p>
      {/each}
    </div>
  </Section>
</div>
