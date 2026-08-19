<script lang="ts">
  import { Popover } from 'bits-ui';
  import { Pane, PaneGroup } from 'paneforge';
  import { fade } from 'svelte/transition';

  import { Info } from '$lib/icons';
  import PaneDivider from '$lib/kit/PaneDivider.svelte';
  import LogViewer from '$lib/LogViewer.svelte';
  import { getVoxelStation } from '$lib/model';
  import PreviewCanvas from '$lib/preview/PreviewCanvas.svelte';
  import PreviewFrameInfo from '$lib/preview/PreviewFrameInfo.svelte';
  import { getPreviewContext } from '$lib/preview/session.svelte';
  import { StageView, type StageViewport } from '$lib/stage';
  import { createPaneSize } from '$lib/utils';

  const app = getVoxelStation();
  const previews = getPreviewContext();
  const preview = $derived(previews.current);

  let stageViewport = $state.raw<StageViewport>({ mode: 'auto' });

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

{#if app.instrument}
  {@const instrument = app.instrument}
  <!-- <main class="min-h-0 min-w-0 flex-1 overflow-hidden"> -->
  <PaneGroup direction="vertical" bind:ref={viewerSplitEl} autoSaveId="shell:workspace:viewer:logs" class="bg-canvas">
    <Pane defaultSize={65} minSize={30} class="flex flex-1 flex-col justify-center">
      <div class="flex h-full flex-col bg-canvas">
        <div class="relative flex min-h-0 flex-1">
          <div class="relative min-w-0 flex-1 overflow-hidden" data-fly-origin>
            {#if preview}
              <div class="absolute top-3 left-3 z-20">
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
  <!-- </main> -->
{:else}
  <LogViewer logs={app.logs} />
{/if}
