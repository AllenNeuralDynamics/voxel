<script lang="ts">
  import { useEventListener, watch } from 'runed';
  import { onMount } from 'svelte';

  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { sendStationWindowRequest, stationWindowRequest } from '$lib/app-windows';
  import { AlertCircleOutline, ChevronRight } from '$lib/icons';
  import { resolveInstrumentView, violationLocation } from '$lib/instruments/instrument-view';
  import OverviewDevices from '$lib/instruments/overview/OverviewDevices.svelte';
  import OverviewImaging from '$lib/instruments/overview/OverviewImaging.svelte';
  import { Button, Field, TextInput } from '$lib/kit';
  import { errorMessage } from '$lib/model';
  import { dashboardInstrumentPath, instrumentPath, stationPath } from '$lib/routes';
  import { displayName, toastError } from '$lib/utils';

  import { getDashboardState } from '../../state.svelte';

  const dashboard = getDashboardState();
  const stationId = $derived(page.params.stationId ?? '');
  const station = $derived(dashboard.stations.find((candidate) => candidate.id === stationId));
  const discovery = $derived(dashboard.discoveries.get(stationId));
  const snapshot = $derived(dashboard.snapshots.get(stationId));
  const activeInstrument = $derived(snapshot?.session?.info.instrument_name ?? null);
  const requestedInstrument = $derived(page.url.searchParams.get('instrument'));
  const templateName = $derived(page.url.searchParams.get('template'));
  const firstInstrument = $derived(
    discovery ? (Object.keys(discovery.instruments).sort((left, right) => left.localeCompare(right))[0] ?? null) : null
  );
  const instrumentName = $derived(requestedInstrument ?? activeInstrument ?? firstInstrument);
  const selection = $derived(
    templateName
      ? ({ kind: 'template', name: templateName } as const)
      : instrumentName
        ? ({ kind: 'instrument', name: instrumentName } as const)
        : null
  );
  const selected = $derived(discovery && selection ? resolveInstrumentView(discovery, selection) : null);

  let instanceName = $state('');
  let actionName = $state<string | null>(null);
  let actionError = $state<string | null>(null);

  onMount(() => toastError(dashboard.loadStation(stationId)));
  useEventListener(window, 'focus', () => toastError(dashboard.loadStation(stationId)));
  watch(
    () => templateName,
    (name) => {
      instanceName = name ?? '';
      actionError = null;
    }
  );
  watch(
    () => instrumentName,
    () => {
      actionError = null;
    }
  );

  function instrumentTarget(name: string) {
    return instrumentPath(stationId, name);
  }

  function sanitize(value: string): string {
    return value.trim().toLowerCase().replace(/\s+/g, '-');
  }

  async function openInstrument(name: string): Promise<void> {
    actionName = name;
    actionError = null;
    const target = instrumentTarget(name);
    const controlWindow = dashboard.acquireStationWindow(stationId, `${target}?open=1`);

    if (!controlWindow) {
      actionError = 'The control window was blocked by the browser.';
      actionName = null;
      return;
    }

    try {
      if (!controlWindow.created) {
        sendStationWindowRequest(controlWindow.ref, stationWindowRequest(stationId, name, true));
      }
    } catch (error) {
      if (controlWindow.created) {
        controlWindow.ref.close();
        dashboard.releaseStationWindow(stationId, controlWindow.ref);
      }
      actionError = errorMessage(error);
    } finally {
      actionName = null;
    }
  }

  async function createInstrument(): Promise<void> {
    if (!templateName) return;
    const name = sanitize(instanceName) || templateName;
    actionName = templateName;
    actionError = null;
    const controlWindow = dashboard.acquireStationWindow(stationId, 'about:blank');

    if (!controlWindow) {
      actionError = 'The control window was blocked by the browser.';
      actionName = null;
      return;
    }

    try {
      await dashboard.createInstrument(stationId, templateName, name);
      const target = instrumentTarget(name);
      if (controlWindow.created) controlWindow.ref.location.href = `${target}?open=1`;
      else sendStationWindowRequest(controlWindow.ref, stationWindowRequest(stationId, name, true));
      await goto(dashboardInstrumentPath(stationId, name), { replaceState: true });
    } catch (error) {
      if (controlWindow.created) {
        controlWindow.ref.close();
        dashboard.releaseStationWindow(stationId, controlWindow.ref);
      }
      actionError = errorMessage(error);
    } finally {
      actionName = null;
    }
  }
</script>

<div class="flex h-full min-h-0 flex-col">
  <header class="flex h-14 shrink-0 items-center gap-4 border-b border-border px-6">
    <nav class="flex min-w-0 flex-1 items-center gap-1.5" aria-label="Breadcrumb">
      <a
        href={stationPath(stationId)}
        class="max-w-[45%] truncate text-fg-muted transition-colors hover:text-fg"
        title={station?.name}
      >
        {station?.name ?? 'Station'}
      </a>
      <ChevronRight width="16" height="16" class="shrink-0 text-fg-faint" />
      <h1 class="min-w-0 truncate text-xl font-medium text-fg" title={selection && displayName(selection.name)}>
        {selection ? displayName(selection.name) : 'No instruments'}
      </h1>
    </nav>

    {#if selection?.kind === 'template'}
      <Button
        class="shrink-0"
        variant="success"
        size="sm"
        disabled={!selected?.config || activeInstrument !== null || actionName !== null}
        onclick={createInstrument}
      >
        {actionName === selection.name ? 'Creating…' : 'Create and open'}
      </Button>
    {:else if selection?.kind === 'instrument'}
      {@const invalid = !selected?.config || selected.errorSource === 'config'}
      <Button
        class="shrink-0"
        size="sm"
        variant={activeInstrument === selection.name ? 'outline' : 'default'}
        disabled={invalid || actionName !== null}
        onclick={() => openInstrument(selection.name)}
      >
        {actionName === selection.name
          ? 'Opening…'
          : activeInstrument === selection.name
            ? 'Open control'
            : activeInstrument
              ? 'Switch instrument'
              : 'Open instrument'}
      </Button>
    {/if}
  </header>

  <div class="min-h-0 flex-1 overflow-y-auto px-6 py-5">
    {#if actionError}
      <div class="mb-5 flex items-start gap-2 rounded-lg border border-danger/40 bg-danger/5 p-3 text-danger">
        <AlertCircleOutline width="17" height="17" class="mt-0.5 shrink-0" />
        <p>{actionError}</p>
      </div>
    {/if}

    {#if selection?.kind === 'template'}
      <section class="mb-6 max-w-xl rounded-lg border border-border bg-card p-4">
        <div class="mb-3 flex items-center gap-2">
          <span class="rounded-full bg-element-bg px-1.5 py-px text-sm text-fg-muted">Template</span>
          <p class="text-fg-muted">Create a new instrument from these defaults.</p>
        </div>
        <Field label="Instrument name" id="new-instrument-name">
          <TextInput
            bind:value={instanceName}
            id="new-instrument-name"
            align="left"
            placeholder={selection.name}
            disabled={actionName !== null}
          />
        </Field>
        {#if activeInstrument}
          <p class="mt-2 text-sm text-fg-muted">
            Close {displayName(activeInstrument)} before creating another instrument.
          </p>
        {/if}
      </section>
    {:else if selection?.kind === 'instrument' && activeInstrument && activeInstrument !== selection.name}
      <div class="mb-5 rounded-lg border border-border bg-element-bg/40 p-3 text-fg-muted">
        The control window will ask before closing {displayName(activeInstrument)} and switching instruments.
      </div>
    {/if}

    {#if dashboard.stationErrors.has(stationId) && !discovery}
      <div class="rounded-lg border border-danger/40 bg-danger/5 p-4 text-danger">
        {dashboard.stationErrors.get(stationId)}
      </div>
    {:else if selected?.config && selected.state}
      {#if selected.errorSource === 'state'}
        <div class="mb-5 rounded-lg border border-warning/40 bg-warning/5 p-3 text-fg-muted">
          The saved state could not be loaded. Showing the configured defaults instead.
        </div>
      {/if}
      <div class="max-w-6xl space-y-6">
        <OverviewImaging imaging={selected.state.imaging} />
        <OverviewDevices hal={selected.config.hal} imaging={selected.state.imaging} />
      </div>
    {:else if selected?.errors.length}
      <section class="max-w-4xl overflow-hidden rounded-lg border border-danger/40 bg-danger/5">
        <div class="flex items-start gap-3 border-b border-danger/25 px-3 py-2.5">
          <AlertCircleOutline width="18" height="18" class="mt-0.5 shrink-0 text-danger" />
          <div>
            <h2 class="text-lg font-medium text-danger">Instrument configuration issue</h2>
            <p class="mt-0.5 text-fg-muted">Resolve these issues before opening this instrument.</p>
          </div>
        </div>
        <ul class="divide-y divide-border/40">
          {#each selected.errors as violation, index (`${violation.code ?? ''}:${violationLocation(violation)}:${index}`)}
            <li class="px-3 py-2">
              {#if violationLocation(violation)}
                <p class="font-mono text-sm break-all text-fg-muted">{violationLocation(violation)}</p>
              {/if}
              <p class="text-danger">{violation.msg}</p>
            </li>
          {/each}
        </ul>
      </section>
    {:else if selection && discovery}
      <p class="text-fg-muted">
        This {selection.kind === 'template' ? 'template' : 'instrument'} is not in the station catalog.
      </p>
    {:else if discovery}
      <div class="rounded-lg border border-dashed border-border p-10 text-center text-fg-muted">
        No instruments are installed on this station.
      </div>
    {:else}
      <p class="text-fg-muted">Loading instrument details…</p>
    {/if}
  </div>
</div>
