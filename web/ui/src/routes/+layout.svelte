<script lang="ts">
  import './layout.css';

  import { createHotkey, createHotkeySequence } from '@tanstack/svelte-hotkeys';
  import { DropdownMenu } from 'bits-ui';
  import { Pane, PaneGroup } from 'paneforge';
  import { useEventListener } from 'runed';
  import type { Component } from 'svelte';
  import { onDestroy, onMount } from 'svelte';

  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import type { Pathname } from '$app/types';
  import favicon from '$lib/assets/favicon.svg';
  import CamerasMonitor from '$lib/devices/CamerasMonitor.svelte';
  import FilterWheelsMonitor from '$lib/devices/FilterWheelsMonitor.svelte';
  import LasersMonitor from '$lib/devices/LasersMonitor.svelte';
  import { provideTaskSelection } from '$lib/grid/selection.svelte';
  import StageCube from '$lib/grid/StageCube.svelte';
  import { Layers, Microscope, TuneVertical, WaveformsIcon } from '$lib/icons';
  import { Button, Dialog, Toaster } from '$lib/kit';
  import PaneDivider from '$lib/kit/PaneDivider.svelte';
  import LogViewer from '$lib/LogViewer.svelte';
  import { setVoxelApp, VoxelApp } from '$lib/model';
  import { PreviewModeToggle, PreviewViewer } from '$lib/preview';
  import ProfileSelector from '$lib/ProfileSelector.svelte';
  import RunButton from '$lib/RunButton.svelte';
  import { AppearanceSheet, themes } from '$lib/themes';
  import { cn, createPaneSize, toastError } from '$lib/utils';
  import VoxelLogo from '$lib/VoxelLogo.svelte';

  import ConnectionSplash from './ConnectionSplash.svelte';
  import LaunchScreen from './LaunchScreen.svelte';

  const { children } = $props();

  const app = new VoxelApp();
  setVoxelApp(app);
  provideTaskSelection();

  onMount(() => {
    if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js');
    toastError(app.initialize());
  });
  onDestroy(() => app.dispose());
  useEventListener(window, 'beforeunload', () => app.dispose());

  const logs = $derived(app.logs);

  // --- Keyboard shortcuts ---

  createHotkey('Alt+P', () => {
    const inst = app.instrument;
    if (!inst) return;
    if (inst.mode === 'preview') inst.preview.stopPreview();
    else inst.preview.startPreview();
  });
  createHotkeySequence(['Mod+K', 'T'], () => (themes.pickerOpen = true));
  createHotkeySequence(['Mod+K', 'Q'], () => {
    if (app.instrument) closeDialogOpen = true;
  });

  // --- Shell nav ---

  let shellRef = $state<HTMLElement | null>(null);
  const leftPane = createPaneSize(() => shellRef, {
    min: 700,
    default: 740,
    fallback: { min: 30, default: 30, max: 50 }
  });
  const rightPane = createPaneSize(() => shellRef, { min: 336, max: 350, fallback: { min: 15, max: 18 } });

  // Vertical split inside the right pane: monitors (top) over the StageCube (bottom).
  let rightSplitEl = $state<HTMLElement | null>(null);
  const stageCubePane = createPaneSize(() => rightSplitEl, {
    default: 280,
    min: 250,
    max: 320,
    fallback: { min: 28, max: 40, default: 32 }
  });

  const navTabs: { id: Pathname; label: string; icon: Component }[] = [
    { id: '/', label: 'Inspect', icon: Microscope },
    { id: '/tune', label: 'Tune', icon: WaveformsIcon },
    { id: '/configure', label: 'Configure', icon: TuneVertical },
    { id: '/plan', label: 'Plan', icon: Layers }
  ];

  const viewId = $derived<Pathname>(
    navTabs.find((t) => t.id !== '/' && page.url.pathname.startsWith(t.id))?.id ??
      (page.url.pathname === '/debug' ? '/debug' : '/')
  );

  function selectView(id: Pathname) {
    if (viewId === id) return;
    goto(resolve(id), { keepFocus: true, noScroll: true });
  }

  // --- Bottom pane (logs) ---

  let bottomPane = $state<Pane | undefined>(undefined);
  const logsOpen = $derived(bottomPane ? !bottomPane.isCollapsed() : false);

  function toggleLogs() {
    if (bottomPane?.isCollapsed()) bottomPane.expand();
    else bottomPane?.collapse();
  }

  // --- Dialog state ---

  let closeDialogOpen = $state(false);
</script>

<svelte:head>
  <link rel="icon" href={favicon} />
</svelte:head>

{#if !app.client.isConnected}
  <ConnectionSplash {app} />
{:else if !app.instrument}
  <LaunchScreen {app} />
{:else}
  {@const instrument = app.instrument}
  {#snippet appMenu()}
    <DropdownMenu.Root>
      <DropdownMenu.Trigger
        class="flex shrink-0 cursor-pointer items-center text-fg-muted transition-colors hover:text-fg"
        title="App menu"
      >
        <VoxelLogo class="size-ui-md" />
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="start"
          sideOffset={8}
          class="z-50 min-w-56 rounded-md border border-border bg-elevated p-1 text-sm shadow-lg outline-none"
        >
          <DropdownMenu.Item
            class="flex cursor-pointer items-center rounded px-2 py-1.5 outline-none hover:bg-element-hover focus:bg-element-hover data-highlighted:bg-element-hover"
            onclick={() => (themes.pickerOpen = true)}
          >
            Change Appearance
            <span class="ml-8 text-xs text-fg-faint">⌘K T</span>
          </DropdownMenu.Item>
          <DropdownMenu.Separator class="my-1 h-px bg-border" />
          <DropdownMenu.Item
            class="flex cursor-pointer items-center rounded px-2 py-1.5 outline-none hover:bg-element-hover focus:bg-element-hover data-disabled:cursor-not-allowed data-disabled:opacity-50 data-highlighted:bg-element-hover"
            disabled={!app.instrument}
            onclick={() => (closeDialogOpen = true)}
          >
            Close Session…
            <span class="ml-8 text-xs text-fg-faint">⌘K Q</span>
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  {/snippet}
  <div bind:this={shellRef} class="h-screen w-full text-fg">
    <PaneGroup direction="horizontal" autoSaveId="shell.v5">
      <!-- Mode controls: nav + routed content + logs -->
      <Pane {...leftPane}>
        <div class="grid h-full grid-rows-[auto_1fr] bg-surface">
          <header class="flex h-15 shrink-0 items-center gap-x-3 border-b border-border px-4">
            {@render appMenu()}
            <nav class="flex h-ui-md items-center gap-x-1 text-fg-muted">
              {#each navTabs as tab (tab.id)}
                {@const Icon = tab.icon}
                {@const active = viewId === tab.id}
                <button
                  onclick={() => selectView(tab.id)}
                  class={cn(
                    'inline-flex h-full cursor-pointer items-center gap-1.5 rounded-md border px-3 text-sm whitespace-nowrap transition-colors',
                    active
                      ? 'border-fg-accent/30 bg-fg-accent/10 text-fg'
                      : 'border-transparent hover:bg-element-hover hover:text-fg'
                  )}
                  title={tab.label}
                >
                  <Icon width="12" height="12" class="shrink-0" />
                  {tab.label}
                </button>
              {/each}
            </nav>
          </header>
          <div class="flex h-full min-h-0 min-w-0 flex-col bg-canvas/35">
            {@render children()}
          </div>
        </div>
      </Pane>
      <PaneDivider direction="vertical" />

      <!-- Viewer: Preview + Logs (centerpiece) -->
      <Pane defaultSize={45}>
        <div class="flex h-full flex-col bg-canvas">
          <header class="flex h-15 shrink-0 items-center justify-between border-b border-border bg-surface px-4">
            <div class="flex items-center gap-2">
              <PreviewModeToggle />
              <button
                onclick={toggleLogs}
                class="inline-flex h-ui-md cursor-pointer items-center rounded-md border border-transparent px-3 text-sm whitespace-nowrap text-fg-muted transition-colors hover:bg-element-hover hover:text-fg"
              >
                {logsOpen ? 'Hide logs' : 'Show logs'}
              </button>
            </div>
            <RunButton {app} />
          </header>
          <main class="min-h-0 flex-1 overflow-hidden">
            <PaneGroup direction="vertical" autoSaveId="shell.viewer">
              <Pane defaultSize={65} minSize={30} class="flex flex-1 flex-col justify-center">
                <PreviewViewer previewer={instrument.preview} fov={instrument.fov} />
              </Pane>
              <PaneDivider direction="horizontal" ondblclick={toggleLogs} />
              <Pane
                bind:this={bottomPane}
                collapsible
                collapsedSize={0}
                defaultSize={35}
                minSize={20}
                maxSize={55}
                class="bg-surface"
              >
                <LogViewer {logs} class="bg-canvas/35" />
              </Pane>
            </PaneGroup>
          </main>
        </div>
      </Pane>
      <PaneDivider direction="vertical" />

      <!-- Monitors: run controls + device telemetry -->
      <Pane defaultSize={16} {...rightPane} class="flex flex-col bg-surface">
        <header class="flex h-15 shrink-0 items-center border-b border-border px-4">
          <ProfileSelector {instrument} size="md" class="w-full" />
        </header>
        <PaneGroup direction="vertical" bind:ref={rightSplitEl} autoSaveId="monitors.v1" class="min-h-0 flex-1">
          <Pane class="min-h-0 bg-canvas/35">
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
            </div>
          </Pane>
          <PaneDivider direction="horizontal" />
          <Pane defaultSize={32} {...stageCubePane} class="min-h-0">
            <StageCube {instrument} class="border-t border-border p-3" />
          </Pane>
        </PaneGroup>
      </Pane>
    </PaneGroup>
  </div>

  <Dialog.Root bind:open={closeDialogOpen}>
    <Dialog.Content size="sm" showCloseButton={false}>
      <Dialog.Header>
        <Dialog.Title>Close Session</Dialog.Title>
      </Dialog.Header>
      <p class="text-sm text-fg-muted">
        Are you sure you want to close the current session? Any unsaved progress will be lost.
      </p>
      <Dialog.Footer>
        <Button variant="ghost" onclick={() => (closeDialogOpen = false)}>Cancel</Button>
        <Button
          variant="danger"
          onclick={() => {
            closeDialogOpen = false;
            app.close();
          }}
        >
          Close Session
        </Button>
      </Dialog.Footer>
    </Dialog.Content>
  </Dialog.Root>
{/if}

<AppearanceSheet bind:open={themes.pickerOpen} />
<Toaster position="bottom-left" />
