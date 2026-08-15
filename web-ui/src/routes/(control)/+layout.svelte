<script lang="ts">
  import { Popover } from 'bits-ui';
  import { Pane, PaneGroup } from 'paneforge';
  import type { Component } from 'svelte';
  import { fade } from 'svelte/transition';

  import { Info } from '$lib/icons';
  import PaneDivider from '$lib/kit/PaneDivider.svelte';
  import LogViewer from '$lib/LogViewer.svelte';
  import { getVoxelApp, type PreviewMode } from '$lib/model';
  import PreviewCanvas from '$lib/preview/PreviewCanvas.svelte';
  import PreviewFrameInfo from '$lib/preview/PreviewFrameInfo.svelte';
  import { getPreviewContext } from '$lib/preview/session.svelte';
  import { StageView, type StageViewport } from '$lib/stage';
  import { cn, createPaneSize } from '$lib/utils';

  const { children } = $props();

  const app = getVoxelApp();
  const previews = getPreviewContext();
  const preview = $derived(previews.current);

  let stageViewport = $state.raw<StageViewport>({ mode: 'auto' });

  type Segment = { key: string; label: string; icon?: Component; active: boolean; select: () => void };

  const previewModes: { mode: PreviewMode; label: string }[] = [
    { mode: 'live', label: 'Live' },
    { mode: 'stage', label: 'Stage' }
  ];

  const modeSegments = $derived<Segment[]>(
    previewModes.map((mode) => ({
      key: mode.mode,
      label: mode.label,
      active: app.viewMode.get() === mode.mode,
      select: () => app.viewMode.set(mode.mode)
    }))
  );

  let workspaceSplitEl = $state<HTMLElement | null>(null);
  const contentPane = createPaneSize(() => workspaceSplitEl, {
    min: 45,
    default: 45,
    max: 64,
    fallback: { min: 30, default: 30, max: 50 }
  });

  let logsPaneRef = $state<Pane | undefined>(undefined);
  const logsOpen = $derived(logsPaneRef ? !logsPaneRef.isCollapsed() : true);
  let logsExpandedSize = 35;
  let viewerSplitEl = $state<HTMLElement | null>(null);
  const collapsedLogPane = createPaneSize(() => viewerSplitEl, {
    collapsed: 2.1,
    fallback: { collapsed: 4 }
  });

  function toggleLogs() {
    if (!logsPaneRef) return;
    if (logsPaneRef.isCollapsed()) {
      logsPaneRef.resize(logsExpandedSize);
    } else {
      logsExpandedSize = logsPaneRef.getSize();
      logsPaneRef.collapse();
    }
  }
</script>

{#snippet segmented(segments: Segment[])}
  <div class="flex h-ui-md items-center rounded-md border border-input bg-canvas/50 p-0.5">
    {#each segments as { key, label, icon: Icon, active, select } (key)}
      <button
        type="button"
        title={label}
        onclick={select}
        class={cn(
          'inline-flex h-full min-w-20 cursor-pointer items-center justify-center gap-1.5 rounded-sm px-4 text-lg whitespace-nowrap transition-colors',
          active ? 'bg-element-selected text-fg shadow-sm' : 'text-fg-muted hover:text-fg'
        )}
      >
        {#if Icon}
          <Icon width="12" height="12" class="shrink-0" />
        {/if}
        {label}
      </button>
    {/each}
  </div>
{/snippet}

<PaneGroup
  direction="horizontal"
  bind:ref={workspaceSplitEl}
  autoSaveId="shell:workspace"
  class="h-full min-h-0 min-w-0 overflow-hidden"
>
  <Pane {...contentPane} class="h-full min-w-0 overflow-hidden bg-surface">
    <div class="flex h-full min-h-0 min-w-0 flex-col">
      {@render children()}
    </div>
  </Pane>
  <PaneDivider direction="vertical" />

  {#if app.instrument}
    {@const instrument = app.instrument}
    <Pane class="flex h-full min-w-0 flex-col overflow-hidden bg-canvas">
      <main class="min-h-0 min-w-0 flex-1 overflow-hidden">
        <PaneGroup direction="vertical" bind:ref={viewerSplitEl} autoSaveId="shell:workspace:viewer:logs">
          <Pane defaultSize={65} minSize={30} class="flex flex-1 flex-col justify-center">
            <div class="flex h-full flex-col bg-canvas">
              <div class="relative flex min-h-0 flex-1">
                <div class="relative min-w-0 flex-1 overflow-hidden" data-fly-origin>
                  <div class="pointer-events-none absolute top-3 left-3 z-20 flex items-center gap-2">
                    <div class="pointer-events-auto">{@render segmented(modeSegments)}</div>
                    {#if preview}
                      <div class="pointer-events-auto">
                        <Popover.Root>
                          <Popover.Trigger
                            class="flex h-ui-md w-ui-md cursor-pointer items-center justify-center rounded-md text-fg-muted transition-colors hover:text-fg"
                            aria-label="Frame info"
                            title="Frame info"
                          >
                            <Info width="14" height="14" />
                          </Popover.Trigger>
                          <Popover.Portal>
                            <Popover.Content
                              class="z-50 min-w-48 rounded border border-border bg-surface p-3 shadow-xl outline-none"
                              side="bottom"
                              align="start"
                              sideOffset={6}
                            >
                              <PreviewFrameInfo previewer={preview} />
                            </Popover.Content>
                          </Popover.Portal>
                        </Popover.Root>
                      </div>
                    {/if}
                  </div>
                  {#if app.viewMode.get() === 'stage'}
                    <div class="absolute inset-0" transition:fade={{ duration: 120 }}>
                      <StageView bind:viewport={stageViewport} />
                    </div>
                  {:else if preview}
                    <div class="absolute inset-0" transition:fade={{ duration: 120 }}>
                      <PreviewCanvas previewer={preview} fov={instrument.fov} />
                    </div>
                  {/if}
                </div>
              </div>
            </div>
          </Pane>
          <PaneDivider direction="horizontal" ondblclick={toggleLogs} />
          <Pane
            bind:this={logsPaneRef}
            {...collapsedLogPane}
            collapsible
            defaultSize={35}
            minSize={20}
            maxSize={55}
            class="min-h-0 bg-surface"
          >
            <LogViewer logs={app.logs} expanded={logsOpen} ontoggle={toggleLogs} class="bg-canvas/35" />
          </Pane>
        </PaneGroup>
      </main>
    </Pane>
  {:else}
    <Pane class="min-h-0 min-w-0 bg-canvas">
      <LogViewer logs={app.logs} />
    </Pane>
  {/if}
</PaneGroup>
