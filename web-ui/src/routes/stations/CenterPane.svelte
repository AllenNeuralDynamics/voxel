<script lang="ts">
  import { Popover } from 'bits-ui';
  import { Pane, PaneGroup } from 'paneforge';
  import { fade } from 'svelte/transition';

  import { Select } from '$lib/kit';
  import PaneDivider from '$lib/kit/PaneDivider.svelte';
  import LogViewer from '$lib/LogViewer.svelte';
  import { getVoxelStation, type PreviewMode } from '$lib/model';
  import { prefs } from '$lib/prefs';
  import PreviewCanvas from '$lib/preview/PreviewCanvas.svelte';
  import PreviewFrameInfo from '$lib/preview/PreviewFrameInfo.svelte';
  import { getPreviewContext } from '$lib/preview/session.svelte';
  import { SPATIAL_UNIT_OPTIONS } from '$lib/spatial-units';
  import { StageControls, StageView, type Viewport } from '$lib/stage';
  import { cn, createPaneSize } from '$lib/utils';

  const app = getVoxelStation();
  const previews = getPreviewContext();
  const preview = $derived(previews.current);
  const previewModes: { mode: PreviewMode; label: string; title?: string }[] = [
    { mode: 'fov', label: 'FOV', title: 'Field of View' },
    { mode: 'stage', label: 'Stage' }
  ];

  let stageViewport = $state.raw<Viewport | null>(null);
  $effect(() => {
    void app.instrument;
    stageViewport = null;
  });

  let logsPaneRef = $state<Pane | undefined>(undefined);
  const logsOpen = $derived(logsPaneRef ? !logsPaneRef.isCollapsed() : true);
  let logsExpandedSize = 35;
  let viewerSplitEl = $state<HTMLElement | null>(null);
  const collapsedLogPane = createPaneSize(() => viewerSplitEl, {
    collapsed: 0,
    fallback: { collapsed: 0 }
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

{#if app.instrument}
  {@const instrument = app.instrument}
  <div class="@container/center-pane flex h-full min-h-0 min-w-0 flex-col bg-canvas">
    <PaneGroup
      direction="vertical"
      bind:ref={viewerSplitEl}
      autoSaveId="shell:workspace:viewer:logs"
      class="min-h-0 flex-1 bg-canvas"
    >
      <Pane defaultSize={65} minSize={30} class="flex flex-1 flex-col justify-center">
        <div class="flex h-full flex-col bg-canvas">
          <div class="relative flex min-h-0 flex-1">
            <div class="relative min-w-0 flex-1 overflow-hidden" data-fly-origin>
              <div class="pointer-events-none absolute top-0 left-3 z-20 flex h-pane-header items-center gap-1">
                <div
                  class="pointer-events-auto flex h-ui-xs items-stretch divide-x divide-control-line overflow-hidden rounded-sm border border-control-line bg-canvas/80 shadow-sm backdrop-blur-sm"
                >
                  {#each previewModes as { mode, label, title } (mode)}
                    <button
                      type="button"
                      {title}
                      aria-label={title ?? label}
                      aria-pressed={app.viewMode.get() === mode}
                      onclick={() => app.viewMode.set(mode)}
                      class={cn(
                        'min-w-14 cursor-pointer px-2 text-base transition-colors',
                        app.viewMode.get() === mode
                          ? 'bg-element-selected text-fg'
                          : 'text-fg-muted hover:bg-element-hover hover:text-fg'
                      )}
                    >
                      {label}
                    </button>
                  {/each}
                </div>
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
        <LogViewer logs={app.logs} expanded={logsOpen} showFooter={false} class="bg-canvas/35" />
      </Pane>
    </PaneGroup>
    <footer
      class="grid min-h-pane-footer shrink-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-2 border-t border-line-muted bg-surface px-3 py-2 @min-[72rem]/center-pane:grid-cols-[minmax(max-content,1fr)_auto_minmax(0,48rem)]"
    >
      <div class="col-start-1 row-start-1 flex items-center gap-2">
        <button
          type="button"
          aria-pressed={logsOpen}
          onclick={toggleLogs}
          class="flex h-6 w-20 shrink-0 cursor-pointer items-center justify-center rounded-md border border-line-faint bg-element-bg px-2 text-sm whitespace-nowrap text-fg-muted transition-colors hover:bg-element-hover hover:text-fg"
        >
          {logsOpen ? 'Hide logs' : 'Show logs'}
        </button>
        {#if preview}
          {@const previewChannels = preview.channels.filter((channel) => channel.name)}
          {@const readyPreviewChannels = previewChannels.filter(
            (channel) => channel.overviewFrame || channel.viewportFrame
          ).length}
          <Popover.Root>
            <Popover.Trigger
              class="flex h-6 shrink-0 cursor-pointer items-center gap-1 rounded-md border border-line-faint bg-element-bg px-2 text-sm whitespace-nowrap text-fg-muted transition-colors hover:bg-element-hover hover:text-fg"
              title="Preview frame information"
            >
              <span>Preview Frames</span>
              {#if preview.error}
                <span class="inline-flex min-w-9 justify-center rounded-full bg-danger/10 px-1.5 text-sm text-danger"
                  >Error</span
                >
              {:else}
                <span class="inline-flex min-w-8 justify-center font-mono tabular-nums">
                  {previewChannels.length ? `${readyPreviewChannels}/${previewChannels.length}` : '—'}
                </span>
              {/if}
            </Popover.Trigger>
            <Popover.Portal>
              <Popover.Content
                class="z-50 min-w-48 rounded border border-line-muted bg-surface p-3 shadow-xl outline-none"
                side="top"
                align="center"
                sideOffset={6}
              >
                <PreviewFrameInfo previewer={preview} />
              </Popover.Content>
            </Popover.Portal>
          </Popover.Root>
        {/if}
      </div>
      <Select
        size="xs"
        class="col-start-2 row-start-1 w-24 justify-self-end"
        prefix="Units"
        value={prefs.spatialUnit.get()}
        options={SPATIAL_UNIT_OPTIONS}
        onchange={(value) => {
          if (value === 'mm' || value === 'um') prefs.spatialUnit.set(value);
        }}
      />
      <StageControls
        stage={instrument.stage}
        class="col-span-2 col-start-1 row-start-2 w-full min-w-0 justify-self-end @min-[72rem]/center-pane:col-span-1 @min-[72rem]/center-pane:col-start-3 @min-[72rem]/center-pane:row-start-1"
      />
    </footer>
  </div>
{:else}
  <LogViewer logs={app.logs} />
{/if}
