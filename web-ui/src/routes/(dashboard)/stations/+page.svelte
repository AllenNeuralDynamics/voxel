<script lang="ts">
  import { watch } from 'runed';

  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { type AcquisitionManifest, type ImagingProtocol, resolveInstrumentView } from '$lib/core/model';
  import { cn, displayName, errorMessage } from '$lib/core/utils';
  import { Badge, Button, Dialog, Field, Select, TextBox } from '$lib/kit';
  import {
    ArrowRight,
    ChevronRight,
    CircleAlert,
    DotsSpinner,
    ExternalLink,
    Eye,
    Plus,
    TriangleAlert,
    X
  } from '$lib/kit/icons';
  import { wavelengthToColor } from '$lib/kit/themes/colors';
  import { acquisitionHref } from '$lib/navigation';
  import { sendStationWindowRequest, stationWindowName, stationWindowRequest } from '$lib/shell/app-windows';

  import { getDashboardState } from './state.svelte';
  import {
    byName,
    currentRun,
    GROUPS,
    isPlainClick,
    RUN_STATUS,
    runName,
    stationGroup,
    type StationItem,
    stationTag,
    volumesDone,
    when
  } from './stations';

  const dashboard = getDashboardState();
  const channelList = new Intl.ListFormat(undefined, { type: 'conjunction' });

  const stations = $derived(
    dashboard.stations
      .map((station): StationItem => {
        const feed = dashboard.snapshots.get(station.id);
        const loadError = dashboard.stationErrors.get(station.id);
        return {
          id: station.id,
          name: station.name,
          feed,
          discovery: dashboard.discoveries.get(station.id),
          runs: (dashboard.acquisitions.get(station.id) ?? []).toSorted(
            (left, right) => Date.parse(right.created_at) - Date.parse(left.created_at)
          ),
          loadError,
          group: stationGroup(feed, loadError)
        };
      })
      .toSorted((left, right) => byName(left.name, right.name))
  );
  const groups = $derived(
    GROUPS.map((group) => ({ ...group, items: stations.filter((station) => station.group === group.key) })).filter(
      (group) => group.items.length > 0
    )
  );
  const selectedId = $derived(page.url.searchParams.get('station'));
  const selected = $derived(stations.find((station) => station.id === selectedId) ?? null);

  function select(id: string | null): void {
    const href = id
      ? resolve(`/(dashboard)/stations?station=${encodeURIComponent(id)}`)
      : resolve('/(dashboard)/stations');
    void goto(href, { replaceState: true, noScroll: true, keepFocus: true });
  }

  function hasIssues(station: StationItem): boolean {
    return Object.values(station.discovery?.instruments ?? {}).some(
      (inspection) => inspection.config.status !== 'loaded' || inspection.violations.length > 0
    );
  }

  function idleText(station: StationItem): string {
    const ended = station.runs.find((run) => run.ended_at)?.ended_at;
    return ended ? `Idle since ${when(ended)}` : 'Idle';
  }

  function previewText(station: StationItem): string {
    const instrument = station.feed?.session?.instrument;
    if (instrument?.activity.kind !== 'preview') return 'Previewing';
    const channels = instrument.activity.channels.map(
      (id) => instrument.imaging.channels[id]?.label ?? displayName(id)
    );
    return channels.length ? `Previewing ${channelList.format(channels)}` : 'Previewing';
  }

  // The side panel of the selected station.
  const BLOCKED = 'The control window was blocked by the browser.';
  const RUNS_SHOWN = 3;

  const peekSession = $derived(selected?.feed?.session ?? null);
  const peekOpen = $derived(peekSession?.info.instrument_name ?? null);
  const peekRun = $derived(selected ? currentRun(selected) : null);
  const peekNames = $derived(
    Object.keys(selected?.discovery?.instruments ?? {}).toSorted((left, right) =>
      left === peekOpen ? -1 : right === peekOpen ? 1 : byName(left, right)
    )
  );
  const templates = $derived(Object.keys(selected?.discovery?.templates ?? {}).toSorted(byName));
  const canCreate = $derived(
    !!selected && !peekSession && !selected.loadError && selected.feed?.status === 'idle' && templates.length > 0
  );
  const peekNote = $derived(
    !selected
      ? null
      : selected.loadError
        ? { tone: 'warning', text: `The dashboard cannot reach this station. ${selected.loadError}` }
        : selected.feed?.status === 'closed'
          ? { tone: 'warning', text: 'This station is closed.' }
          : selected.feed?.error
            ? { tone: 'danger', text: selected.feed.error }
            : null
  );

  let actionError = $state<string | null>(null);
  let creating = $state(false);
  let newOpen = $state(false);
  let template = $state<string | null>(null);
  let newName = $state('');

  watch(
    () => selected?.id,
    () => {
      actionError = null;
      newOpen = false;
    }
  );

  function details(station: StationItem, name: string) {
    const saved = station.discovery ? resolveInstrumentView(station.discovery, { kind: 'instrument', name }) : null;
    const isOpen = name === peekOpen;
    const imaging: ImagingProtocol | undefined =
      isOpen && peekSession ? peekSession.instrument.imaging : saved?.state?.imaging;
    const runs = station.runs.filter((candidate) => candidate.instrument === name);
    return { saved, isOpen, imaging, runs };
  }

  function channelLabel(imaging: ImagingProtocol, id: string): string {
    return imaging.channels[id]?.label ?? displayName(id);
  }

  function show(station: StationItem, instrument: string): void {
    try {
      actionError = dashboard.showInstrument(station.id, instrument) ? null : BLOCKED;
    } catch (error) {
      actionError = errorMessage(error);
    }
  }

  function startNew(): void {
    template ??= templates[0] ?? null;
    newName = '';
    actionError = null;
    newOpen = true;
  }

  async function createInstrument(): Promise<void> {
    const station = selected;
    if (!station || !template) return;
    const name = newName.trim().toLowerCase().replace(/\s+/g, '-') || template;
    creating = true;
    actionError = null;
    const controlWindow = dashboard.acquireStationWindow(station.id, 'about:blank');
    if (!controlWindow) {
      actionError = BLOCKED;
      creating = false;
      return;
    }
    try {
      await dashboard.createInstrument(station.id, template, name);
      const target = resolve('/stations/[stationId]/instruments/[instrumentId]', {
        stationId: station.id,
        instrumentId: name
      });
      if (controlWindow.created) controlWindow.ref.location.href = `${target}?open=1`;
      else sendStationWindowRequest(controlWindow.ref, stationWindowRequest(station.id, name, true));
      newOpen = false;
    } catch (error) {
      if (controlWindow.created) {
        controlWindow.ref.close();
        dashboard.releaseStationWindow(station.id, controlWindow.ref);
      }
      actionError = errorMessage(error);
    } finally {
      creating = false;
    }
  }
</script>

{#snippet runProgress(stationId: string, run: AcquisitionManifest)}
  {@const done = volumesDone(run)}
  {@const total = run.volumes.length}
  <span class="flex min-w-0 items-center gap-3">
    <a
      href={resolve('/stations/[stationId]/instruments/[instrumentId]', { stationId, instrumentId: run.instrument })}
      target={stationWindowName(stationId)}
      class="relative z-10 min-w-0 truncate rounded-sm font-mono font-medium text-fg underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-focus"
      title="Show the run in the station window"
      onclick={(event) => {
        if (isPlainClick(event) && dashboard.showInstrument(stationId, run.instrument)) event.preventDefault();
      }}>{runName(run)}</a
    >
    <span
      class="h-1.5 w-24 shrink-0 overflow-hidden rounded-full bg-track"
      role="progressbar"
      aria-label="Volumes done"
      aria-valuemin={0}
      aria-valuemax={total}
      aria-valuenow={done}
    >
      <span class="block h-full rounded-full bg-accent" style:width="{total ? (done / total) * 100 : 0}%"></span>
    </span>
    <span class="shrink-0 text-sm text-fg-muted tabular-nums">{done} of {total}</span>
  </span>
{/snippet}

{#snippet status(station: StationItem)}
  {@const feed = station.feed}
  {@const run = currentRun(station)}
  {#if station.group === 'away'}
    <span class="text-fg-muted">{station.loadError ? 'Not reachable' : 'Closed'}</span>
  {:else if station.group === 'fix'}
    <span class="flex min-w-0 items-center gap-1.5 text-danger-fg">
      <CircleAlert class="size-3.5 shrink-0" /><span class="truncate">{feed?.error ?? 'Faulted'}</span>
    </span>
  {:else if run}
    {@render runProgress(station.id, run)}
  {:else if station.group === 'running'}
    <span class="flex items-center gap-1.5 text-fg-muted"><DotsSpinner class="size-3.5" />Acquiring</span>
  {:else if feed?.status === 'opening' || feed?.status === 'closing'}
    <span class="flex items-center gap-1.5 text-fg-muted">
      <DotsSpinner class="size-3.5" />{feed.status === 'opening' ? 'Opening' : 'Closing'}
    </span>
  {:else if feed?.session?.instrument.activity.kind === 'preview'}
    <span class="flex min-w-0 items-center gap-1.5 text-fg-muted">
      <Eye class="size-3.5 shrink-0" /><span class="truncate">{previewText(station)}</span>
    </span>
  {:else}
    <span class="text-fg-muted">{idleText(station)}</span>
  {/if}
{/snippet}

{#snippet peek(station: StationItem)}
  {@const tag = stationTag(station)}
  <header class="flex min-h-12 shrink-0 items-center gap-2 border-b border-line-faint py-2 pr-2 pl-4">
    <h2 class="min-w-0 truncate text-xl font-medium" id="station-peek-title">{station.name}</h2>
    {#if tag}<Badge tone={tag.tone}>{tag.label}</Badge>{/if}
    <span class="flex-1"></span>
    {#if !station.loadError && peekNames[0]}
      <Button variant="ghost" size="md" class="text-fg-muted" onclick={() => show(station, peekNames[0])}>
        Operate<ExternalLink class="size-3.5" />
      </Button>
    {/if}
    <Button
      variant="ghost"
      size="icon"
      class="text-fg-muted"
      title="Close"
      aria-label="Close {station.name}"
      onclick={() => select(null)}
    >
      <X class="size-4" />
    </Button>
  </header>

  <div class="min-h-0 flex-1 overflow-y-auto px-4 pt-3.5 pb-4">
    <div class="flex flex-col gap-3">
      {#if actionError && !newOpen}
        <p class="flex items-start gap-2 note-danger p-3 text-danger-fg">
          <CircleAlert class="mt-0.5 size-4 shrink-0" />{actionError}
        </p>
      {/if}
      {#if peekNote}
        <p
          class={[
            'flex items-start gap-2 p-3',
            peekNote.tone === 'danger' ? 'note-danger text-danger-fg' : 'note-warning text-warning-fg'
          ]}
        >
          <CircleAlert class="mt-0.5 size-4 shrink-0" />{peekNote.text}
        </p>
      {/if}

      {#each peekNames as name (name)}
        {@const card = details(station, name)}
        {@const issue = card.isOpen ? null : card.saved?.errors[0]}
        <article class="flex flex-col gap-3 frame-bordered px-4 pt-3 pb-3.5">
          <div class="flex items-center gap-2">
            <h3 class="min-w-0 flex-1 truncate font-medium">
              <a
                href={resolve('/stations/[stationId]/instruments/[instrumentId]', {
                  stationId: station.id,
                  instrumentId: name
                })}
                target={stationWindowName(station.id)}
                class="rounded-sm underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-focus"
                title="Show {displayName(name)} in the station window"
                onclick={(event) => {
                  if (!isPlainClick(event)) return;
                  event.preventDefault();
                  show(station, name);
                }}>{displayName(name)}</a
              >
            </h3>
            {#if card.isOpen && peekSession}
              {@const kind = peekSession.instrument.activity.kind}
              <span class="flex shrink-0 items-center gap-1.5 text-sm text-fg-muted">
                {#if kind === 'capture'}
                  <DotsSpinner class="size-3.5" />Acquiring
                {:else if kind === 'preview'}
                  <Eye class="size-3.5" />Previewing
                {:else}
                  <span class="size-1.5 rounded-full bg-current"></span>Open
                {/if}
              </span>
            {:else if issue}
              <span class="flex shrink-0 items-center gap-1.5 text-sm text-warning-fg">
                <TriangleAlert class="size-3.5" />{card.saved?.errorSource === 'state' ? 'State issue' : 'Config issue'}
              </span>
            {/if}
          </div>

          {#if issue}
            <p class="text-warning-fg">{issue.msg}</p>
          {/if}
          {#if card.isOpen && peekRun}
            {@render runProgress(station.id, peekRun)}
          {/if}

          {#if card.imaging}
            {@const imaging = card.imaging}
            <table class="w-full table-fixed">
              <caption class="sr-only">Channels of {displayName(name)}</caption>
              <thead>
                <tr class="text-left text-sm text-fg-muted">
                  <th class="border-b border-line-faint pb-1 font-normal">Channels</th>
                  <th class="w-18 border-b border-line-faint pb-1 text-right font-normal">Emission</th>
                </tr>
              </thead>
              <tbody>
                {#each Object.entries(imaging.channels) as [channelId, channel] (channelId)}
                  <tr>
                    <th scope="row" class="py-1 text-left font-normal">
                      <span class="flex min-w-0 items-center gap-2">
                        <span
                          class="size-1.5 shrink-0 rounded-full bg-line-muted"
                          style:background-color={channel.emission ? wavelengthToColor(channel.emission) : undefined}
                        ></span>
                        <span class="truncate">{channelLabel(imaging, channelId)}</span>
                      </span>
                    </th>
                    <td class="py-1 text-right text-fg-muted tabular-nums">
                      {channel.emission ? `${channel.emission} nm` : ''}
                    </td>
                  </tr>
                {:else}
                  <tr><td colspan="2" class="py-1 text-fg-muted">None</td></tr>
                {/each}
              </tbody>
            </table>
            <table class="w-full table-fixed">
              <caption class="sr-only">Profiles of {displayName(name)} and the channels each profile uses</caption>
              <thead>
                <tr class="text-left text-sm text-fg-muted">
                  <th class="w-[42%] border-b border-line-faint pb-1 font-normal">Profiles</th>
                  <th class="border-b border-line-faint pb-1 text-right font-normal">Channels</th>
                </tr>
              </thead>
              <tbody>
                {#each Object.entries(imaging.profiles) as [profileId, profile] (profileId)}
                  <tr class="align-top">
                    <th scope="row" class="py-1 text-left font-normal">{profile.label ?? displayName(profileId)}</th>
                    <td class="py-1 pl-3 text-fg-muted">
                      <span class="flex flex-wrap justify-end gap-x-1">
                        {#each profile.channels as channelId, index (channelId)}
                          <span class="whitespace-nowrap"
                            >{channelLabel(imaging, channelId)}{index < profile.channels.length - 1 ? ',' : ''}</span
                          >
                        {/each}
                      </span>
                    </td>
                  </tr>
                {:else}
                  <tr><td colspan="2" class="py-1 text-fg-muted">None</td></tr>
                {/each}
              </tbody>
            </table>
          {/if}
          <div class="flex flex-col">
            <table class="w-full table-fixed">
              <caption class="sr-only">Recent runs of {displayName(name)}</caption>
              <thead>
                <tr class="text-left text-sm text-fg-muted">
                  <th class="border-b border-line-faint pb-1 font-normal">Recent runs</th>
                  <th class="w-7 border-b border-line-faint pb-1 font-normal"><span class="sr-only">Status</span></th>
                  <th class="w-28 border-b border-line-faint pb-1 text-right font-normal">Ended</th>
                </tr>
              </thead>
              <tbody>
                {#each card.runs.slice(0, RUNS_SHOWN) as past (past.id)}
                  {@const runStatus = RUN_STATUS[past.status]}
                  <tr>
                    <td class="py-1">
                      <a
                        href={acquisitionHref({ stationId: station.id, instrumentId: name }, past.id)}
                        target={stationWindowName(station.id)}
                        class="block truncate rounded-sm font-mono underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-focus"
                        >{runName(past)}</a
                      >
                    </td>
                    <td class="py-1">
                      <span role="img" aria-label={runStatus.label} title={runStatus.label} class="flex justify-center">
                        <runStatus.icon class="size-3.5 {runStatus.color}" aria-hidden="true" />
                      </span>
                    </td>
                    <td class="py-1 text-right text-fg-muted tabular-nums">
                      {when(past.ended_at ?? past.started_at ?? past.created_at)}
                    </td>
                  </tr>
                {:else}
                  <tr><td colspan="3" class="py-1 text-fg-muted">None yet</td></tr>
                {/each}
              </tbody>
            </table>
            {#if card.runs.length}
              <a
                href={resolve('/stations/[stationId]/instruments/[instrumentId]/history', {
                  stationId: station.id,
                  instrumentId: name
                })}
                target={stationWindowName(station.id)}
                class="mt-1 inline-flex items-center gap-1 self-start rounded-sm text-sm text-fg-muted hover:text-fg focus-visible:outline-2 focus-visible:outline-focus"
                >{card.runs.length}
                {card.runs.length === 1 ? 'run' : 'runs'}<ArrowRight class="size-3" aria-hidden="true" /></a
              >
            {/if}
          </div>
        </article>
      {:else}
        {#if station.discovery}
          <p class="frame-placeholder p-6 text-center text-fg-muted">No instruments are installed on this station.</p>
        {/if}
      {/each}

      {#if canCreate}
        <Button variant="ghost" size="md" class="-ml-2 self-start text-fg-muted" onclick={startNew}>
          <Plus class="size-3.5" />New instrument
        </Button>
      {/if}
    </div>
  </div>

  <Dialog.Root bind:open={newOpen}>
    <Dialog.Content size="sm">
      <Dialog.Header>
        <Dialog.Title>New instrument on {station.name}</Dialog.Title>
      </Dialog.Header>
      <form
        class="grid gap-3"
        onsubmit={(event) => {
          event.preventDefault();
          void createInstrument();
        }}
      >
        <Field label="Template" id="new-instrument-template">
          <Select
            id="new-instrument-template"
            value={template}
            options={templates}
            formatLabel={displayName}
            onChange={(value) => (template = value)}
            size="lg"
            disabled={creating}
          />
        </Field>
        <Field label="Name" id="new-instrument-name">
          <TextBox
            live
            size="lg"
            id="new-instrument-name"
            value={newName}
            onChange={(text) => (newName = text)}
            placeholder={template ?? ''}
            disabled={creating}
          />
        </Field>
        {#if actionError}
          <p class="note-danger p-3 text-danger-fg">{actionError}</p>
        {/if}
        <Dialog.Footer>
          <Button type="button" variant="secondary" size="md" onclick={() => (newOpen = false)}>Cancel</Button>
          <Button type="submit" size="md" loading={creating} disabled={!template}>Create and open</Button>
        </Dialog.Footer>
      </form>
    </Dialog.Content>
  </Dialog.Root>
{/snippet}

<h1 class="sr-only">Stations</h1>

<div class="pt-3 pb-8">
  {#if dashboard.loading && dashboard.stations.length === 0}
    <p class="text-fg-muted">Loading stations…</p>
  {:else if dashboard.error && dashboard.stations.length === 0}
    <p class="max-w-lg note-danger p-4 text-danger-fg">{dashboard.error}</p>
  {:else if dashboard.stations.length === 0}
    <p class="frame-placeholder p-10 text-center text-fg-muted">No stations are available.</p>
  {:else}
    <div
      class={cn('grid items-start gap-4', selected && 'lg:grid-cols-[minmax(0,1fr)_var(--peek-width)]')}
      style:--peek-width="clamp(27rem, 33vw, 34rem)"
    >
      <div class="flex min-w-0 flex-col gap-5">
        {#each groups as group (group.key)}
          <section aria-labelledby="group-{group.key}">
            <h2 id="group-{group.key}" class="flex items-center gap-2 px-0.5 pb-1.5 text-sm text-fg-muted">
              {group.title}<span class="tabular-nums">{group.items.length}</span>
            </h2>
            <ul class="flex flex-col divide-y divide-line-faint frame-raised p-1">
              {#each group.items as station (station.id)}
                {@const open = station.feed?.session?.info.instrument_name}
                {@const tag = stationTag(station)}
                {@const isSelected = station.id === selected?.id}
                <li class="mx-2">
                  <div
                    class={cn(
                      'relative -mx-2 grid min-h-[2.75rem] grid-cols-[minmax(0,24rem)_minmax(0,1fr)_auto] items-center gap-x-6 rounded-md px-2.5 py-2 transition-colors',
                      isSelected ? 'bg-element-selected' : 'hover:bg-tint'
                    )}
                  >
                    <button
                      type="button"
                      class="flex min-w-0 items-baseline gap-1.5 text-left text-fg outline-none after:absolute after:inset-0 after:rounded-md focus-visible:after:outline-2 focus-visible:after:outline-focus"
                      aria-expanded={isSelected}
                      aria-controls="station-peek"
                      onclick={() => select(station.id)}
                    >
                      <span class="shrink-0 font-medium">{station.name}</span>
                      {#if open}
                        <span class="text-fg-faint" aria-hidden="true">/</span>
                        <span class="truncate text-fg-muted">{displayName(open)}</span>
                      {/if}
                    </button>
                    <div class="min-w-0">{@render status(station)}</div>
                    <span class="flex items-center gap-3">
                      {#if tag}<Badge tone={tag.tone}>{tag.label}</Badge>{/if}
                      {#if hasIssues(station)}
                        <span role="img" aria-label="An instrument has issues" title="An instrument has issues">
                          <TriangleAlert class="size-3.5 text-warning-fg" />
                        </span>
                      {/if}
                      <ChevronRight class="size-3.5 text-fg-faint" aria-hidden="true" />
                    </span>
                  </div>
                </li>
              {/each}
            </ul>
          </section>
        {/each}
      </div>
      {#if selected}
        <aside
          id="station-peek"
          aria-labelledby="station-peek-title"
          class="fixed inset-y-0 right-0 z-30 flex w-[min(var(--peek-width),100vw)] flex-col overflow-hidden frame-dialog frame-docked-top frame-docked-right frame-docked-bottom lg:sticky lg:top-[calc(var(--app-bar-height)+var(--spacing)*3)] lg:right-auto lg:bottom-auto lg:z-auto lg:h-[calc(100dvh-var(--app-bar-height)-var(--spacing)*3-1rem)] lg:w-auto lg:frame-raised"
        >
          {@render peek(selected)}
        </aside>
      {/if}
    </div>
  {/if}
</div>
