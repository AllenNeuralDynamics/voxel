<script lang="ts">
  import './layout.css';

  import { createHotkey, createHotkeySequence } from '@tanstack/svelte-hotkeys';
  import { Pane, PaneGroup } from 'paneforge';
  import { useEventListener, watch } from 'runed';
  import { onDestroy, onMount, untrack } from 'svelte';

  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import type { Pathname } from '$app/types';
  import favicon from '$lib/assets/favicon.svg';
  import DefaultConfigDialog from '$lib/DefaultConfigDialog.svelte';
  import CamerasMonitor from '$lib/devices/CamerasMonitor.svelte';
  import FilterWheelsMonitor from '$lib/devices/FilterWheelsMonitor.svelte';
  import LasersMonitor from '$lib/devices/LasersMonitor.svelte';
  import RoutingMonitor from '$lib/devices/RoutingMonitor.svelte';
  import { provideTaskSelection } from '$lib/grid/selection.svelte';
  import { Logout, Microscope } from '$lib/icons';
  import { Button, Dialog, Toaster } from '$lib/kit';
  import PaneDivider from '$lib/kit/PaneDivider.svelte';
  import { setVoxelApp, VoxelApp } from '$lib/model';
  import { PreviewSession, providePreviewContext } from '$lib/preview/session.svelte';
  import ProfileSelector from '$lib/ProfileSelector.svelte';
  import RunButton from '$lib/RunButton.svelte';
  import StageGizmo from '$lib/stage/StageGizmo.svelte';
  import { AppearanceSheet, themes } from '$lib/themes';
  import { cn, createPaneSize, pref, sanitizeString, toastError } from '$lib/utils';
  import VoxelLogo from '$lib/VoxelLogo.svelte';

  import ConnectionSplash from './ConnectionSplash.svelte';

  const { children } = $props();

  const app = new VoxelApp();
  setVoxelApp(app);
  const previews = providePreviewContext();
  provideTaskSelection();

  $effect(() => {
    const instrument = app.instrument;
    if (!instrument) {
      previews.current = null;
      return;
    }
    const session = untrack(
      () =>
        new PreviewSession({
          client: app.client,
          instrumentId: instrument.id,
          discovery: app.discovery.preview,
          detection: instrument.hal.detection,
          initialStatus: instrument.status,
          catalog: app.discovery.colormaps
        })
    );
    previews.current = session;
    return () => {
      if (previews.current === session) previews.current = null;
      session.dispose();
    };
  });

  async function configureServiceWorker(): Promise<void> {
    if (!('serviceWorker' in navigator)) return;
    if (import.meta.env.DEV) {
      const registrations = await navigator.serviceWorker.getRegistrations();
      await Promise.all(registrations.map((registration) => registration.unregister()));
      return;
    }
    await navigator.serviceWorker.register('/sw.js');
  }

  onMount(() => {
    toastError(configureServiceWorker());
    toastError(app.initialize());
  });
  onDestroy(() => {
    previews.current?.dispose();
    app.dispose();
  });
  useEventListener(window, 'beforeunload', () => {
    previews.current?.dispose();
    app.dispose();
  });

  // --- Keyboard shortcuts ---

  createHotkey('Alt+P', () => {
    const inst = app.instrument;
    const preview = previews.current;
    if (!inst || !preview) return;
    if (inst.mode === 'preview') preview.stopPreview();
    else preview.startPreview();
  });
  createHotkeySequence(['Mod+K', 'T'], () => (themes.pickerOpen = true));
  createHotkeySequence(['Mod+K', 'Q'], () => {
    if (app.instrument) closeDialogOpen = true;
  });

  // --- Shell nav ---

  let shellRef = $state<HTMLElement | null>(null);

  type Route = { id: Pathname; label: string };
  type Segment = {
    key: string;
    label: string;
    highlighted: boolean;
    select: () => void;
  };

  const libraryRoute: Route = { id: '/', label: 'Library' };
  const controlRoutes: Route[] = [
    { id: '/inspect', label: 'Inspect' },
    { id: '/sync', label: 'Sync' },
    { id: '/configure', label: 'Configure' },
    { id: '/plan', label: 'Plan' },
    { id: '/run', label: 'Run' }
  ];
  const navRoutes = [libraryRoute, ...controlRoutes];
  const lastLibraryRoute = pref<string>('nav:last-library-route', '/');
  const lastInspectRoutes = pref<Record<string, string>>('nav:last-inspect-routes', {});

  function isRememberedLibraryRoute(pathname: string): boolean {
    return (
      pathname === '/' ||
      pathname === '/settings' ||
      pathname.startsWith('/acquisitions/') ||
      (pathname.startsWith('/instruments/') && !pathname.startsWith('/instruments/new/'))
    );
  }

  const libraryTarget = $derived<Pathname>(
    (isRememberedLibraryRoute(lastLibraryRoute.get()) ? lastLibraryRoute.get() : '/') as Pathname
  );

  function isValidInspectRoute(target: string): boolean {
    const instrument = app.instrument;
    if (!instrument) return false;

    const url = new URL(target, page.url.origin);
    if (url.origin !== page.url.origin || url.hash) return false;

    if (url.pathname === '/inspect') {
      const params = [...url.searchParams.entries()];
      return (
        params.length === 0 ||
        (params.length === 1 && params[0][0] === 'axis' && ['x', 'y', 'z'].includes(params[0][1]))
      );
    }

    if (url.search || !url.pathname.startsWith('/inspect/devices/')) return false;
    const encodedId = url.pathname.slice('/inspect/devices/'.length);
    if (!encodedId || encodedId.includes('/')) return false;

    try {
      return instrument.devices.has(decodeURIComponent(encodedId));
    } catch {
      return false;
    }
  }

  const inspectTarget = $derived.by<string>(() => {
    const name = app.activeName;
    if (!name) return '/inspect';
    const target = lastInspectRoutes.get()[name];
    return target && isValidInspectRoute(target) ? target : '/inspect';
  });

  const viewId = $derived<Pathname>(
    navRoutes.find((route) => route.id !== libraryRoute.id && page.url.pathname.startsWith(route.id))?.id ??
      (page.url.pathname === '/debug' ? '/debug' : libraryRoute.id)
  );
  const controlActive = $derived(controlRoutes.some((route) => route.id === viewId));

  watch(
    () => [app.activeTarget, controlActive] as const,
    ([activeTarget, isControlRoute]) => {
      if (activeTarget === null && isControlRoute) goto(resolve(libraryTarget), { replaceState: true });
    }
  );

  watch(
    () => page.url.pathname,
    (pathname) => {
      if (isRememberedLibraryRoute(pathname)) lastLibraryRoute.set(pathname);
    }
  );

  watch(
    () => [app.activeName, page.url.pathname, page.url.search] as const,
    ([name, pathname, search]) => {
      if (!name || !pathname.startsWith('/inspect')) return;
      const target = `${pathname}${search}`;
      if (!isValidInspectRoute(target)) return;

      const routes = lastInspectRoutes.get();
      if (routes[name] !== target) lastInspectRoutes.set({ ...routes, [name]: target });
    }
  );

  function selectView(id: Pathname) {
    if (viewId === id) return;
    const target = id === '/inspect' ? inspectTarget : id;
    goto(resolve(target as Pathname), { keepFocus: true, noScroll: true });
  }

  async function closeInstrument(): Promise<void> {
    const name = app.activeName;
    if (!name) return;
    const previous = lastLibraryRoute.get();
    const target = `/instruments/${encodeURIComponent(name)}` as Pathname;
    lastLibraryRoute.set(target);
    try {
      await app.close();
      await goto(resolve(target), { keepFocus: true, noScroll: true });
    } catch (error) {
      lastLibraryRoute.set(previous);
      throw error;
    }
  }

  const controlSegments = $derived<Segment[]>(
    controlRoutes.map((route) => ({
      key: route.id,
      label: route.label,
      highlighted: viewId === route.id,
      select: () => selectView(route.id)
    }))
  );

  // Pane sizes

  const monitorsPane = createPaneSize(() => shellRef, {
    min: 30,
    default: 30,
    max: 30,
    fallback: { min: 15, max: 18 }
  });

  // Vertical split inside the monitors pane: telemetry (top) over the stage gizmo (bottom).
  let monitorsSplitEl = $state<HTMLElement | null>(null);
  const gizmoPane = createPaneSize(() => monitorsSplitEl, {
    default: 22,
    min: 18,
    max: 28,
    fallback: { min: 28, max: 40, default: 32 }
  });

  // --- Dialog state ---

  let closeDialogOpen = $state(false);
</script>

<svelte:head>
  <link rel="icon" href={favicon} />
</svelte:head>

{#if !app.client.isConnected || !app.ready}
  <ConnectionSplash {app} />
{:else}
  {#snippet routeLink(segment: Segment)}
    <button
      type="button"
      title={segment.label}
      onclick={segment.select}
      class={cn(
        'inline-flex h-full cursor-pointer items-center justify-center px-3 text-lg font-normal whitespace-nowrap transition-colors',
        segment.highlighted ? 'bg-element-selected text-fg' : 'text-fg hover:bg-element-hover/80 hover:text-fg'
      )}
    >
      {segment.label}
    </button>
  {/snippet}
  <div bind:this={shellRef} class="h-screen w-full text-fg">
    <PaneGroup direction="horizontal" autoSaveId="shell:frame">
      <!-- Application workspace below the global navigation. -->
      <Pane class="grid h-full min-w-0 grid-rows-[auto_1fr] overflow-hidden">
        <header class="flex h-12 shrink-0 items-center gap-x-5 border-b border-border bg-elevated px-4">
          <a
            href={resolve(libraryTarget)}
            class={cn(
              '-ml-2 flex h-ui-md shrink-0 items-center gap-2 rounded-md border border-border px-2 text-fg transition-colors',
              viewId === '/' ? 'border-border bg-element-selected' : 'hover:bg-element-hover'
            )}
            title="Library"
            aria-label="Library"
          >
            <VoxelLogo class="size-6 shrink-0" />
            <span class="text-2xl font-normal tracking-wide uppercase">Voxel</span>
          </a>
          {#if app.instrument}
            <div
              class={cn(
                'flex h-ui-md min-w-110 items-stretch overflow-hidden rounded-md border',
                controlActive ? 'border-border' : 'border-border-faint'
              )}
            >
              <nav
                aria-label="Instrument controls"
                class="grid h-full flex-1 auto-cols-fr grid-flow-col divide-x divide-border"
              >
                {#each controlSegments as segment (segment.key)}
                  {@render routeLink(segment)}
                {/each}
              </nav>
            </div>
            <div class="ml-auto flex max-w-2xl min-w-0 flex-1 gap-4">
              <ProfileSelector instrument={app.instrument} size="md" class="min-w-0 flex-3" />
              <RunButton {app} class="w-56 justify-center" />
            </div>
          {:else}
            <span
              class="ml-auto flex h-ui-md w-sm items-center gap-1.5 rounded-md border border-border-faint px-3 text-lg font-normal text-fg-muted"
            >
              <Microscope width="12" height="12" class="shrink-0" />
              No active instrument
            </span>
          {/if}
        </header>
        <div class="h-full min-h-0 min-w-0 overflow-hidden">
          {@render children()}
        </div>
      </Pane>

      {#if app.instrument}
        {@const instrument = app.instrument}
        <PaneDivider direction="vertical" />

        <!-- Active instrument identity + device telemetry -->
        <Pane {...monitorsPane} class="flex flex-col bg-surface">
          <header class="flex h-12 shrink-0 items-center gap-2 border-b border-border bg-elevated px-4">
            <Microscope width="14" height="14" class="shrink-0 text-fg-muted" />
            <span class="min-w-0 flex-1 truncate text-lg" title={sanitizeString(app.activeName ?? '')}>
              {sanitizeString(app.activeName ?? 'Active instrument')}
            </span>
            <button
              type="button"
              title="Close instrument"
              aria-label="Close instrument"
              onclick={() => (closeDialogOpen = true)}
              class="flex size-7 shrink-0 cursor-pointer items-center justify-center rounded text-fg-muted transition-colors hover:bg-element-hover/80 hover:text-danger"
            >
              <Logout width="14" height="14" />
            </button>
          </header>
          <PaneGroup direction="vertical" bind:ref={monitorsSplitEl} autoSaveId="shell:monitors" class="min-h-0 flex-1">
            <Pane class="min-h-0">
              <div class="flex h-full flex-col divide-y divide-border overflow-y-auto">
                {#if instrument.cameras.size > 0}
                  <CamerasMonitor {instrument} />
                {/if}
                {#if instrument.lasers.size > 0}
                  <LasersMonitor {instrument} />
                {/if}
                {#if instrument.filterWheels.length > 0}
                  <FilterWheelsMonitor {instrument} />
                {/if}
                {#if Object.keys(instrument.hal.optical_routing).length > 0}
                  <RoutingMonitor {instrument} />
                {/if}
              </div>
            </Pane>
            <PaneDivider direction="horizontal" />
            <Pane defaultSize={32} {...gizmoPane} class="min-h-0">
              <StageGizmo stage={instrument.stage} class="border-t border-border p-3" />
            </Pane>
          </PaneGroup>
        </Pane>
      {/if}
    </PaneGroup>
  </div>

  <Dialog.Root bind:open={closeDialogOpen}>
    <Dialog.Content size="sm" showCloseButton={false}>
      <Dialog.Header>
        <Dialog.Title>Close instrument</Dialog.Title>
      </Dialog.Header>
      <p class="text-lg text-fg-muted">
        Are you sure you want to close
        <span class="font-medium text-fg">{sanitizeString(app.activeName ?? 'the active instrument')}</span>? Its
        hardware will be disconnected.
      </p>
      <Dialog.Footer>
        <Button variant="ghost" onclick={() => (closeDialogOpen = false)}>Cancel</Button>
        <Button
          variant="danger"
          onclick={() => {
            closeDialogOpen = false;
            toastError(closeInstrument());
          }}
        >
          Close instrument
        </Button>
      </Dialog.Footer>
    </Dialog.Content>
  </Dialog.Root>
{/if}

<AppearanceSheet bind:open={themes.pickerOpen} />
<DefaultConfigDialog />
<Toaster position="bottom-left" />
