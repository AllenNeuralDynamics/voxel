<script lang="ts">
  import { untrack } from 'svelte';
  import { fade } from 'svelte/transition';

  import { getPreviewContext, getVoxelStation } from '$lib/context.svelte';
  import { type CenterPanelTab, prefs, type ViewerMode } from '$lib/core/prefs';
  import { propertyChanges } from '$lib/features/imaging/changes';
  import PropertyChanges from '$lib/features/imaging/PropertyChanges.svelte';
  import { issues, LEVEL_DOT } from '$lib/features/issues';
  import IssueViewer from '$lib/features/issues/IssueViewer.svelte';
  import LogViewer from '$lib/features/issues/LogViewer.svelte';
  import PreviewCanvas from '$lib/features/preview/PreviewCanvas.svelte';
  import PreviewFrameInfo from '$lib/features/preview/PreviewFrameInfo.svelte';
  import { StageView, type Viewport } from '$lib/features/stage';
  import { Button, RadioBar, Spinner } from '@voxel/kit';
  import { cn } from '@voxel/kit/cn';
  import { reportFailure } from '@voxel/kit/failures';
  import { Power } from '@voxel/kit/icons';
  import { createPaneSize, Pane, PaneGroup } from '@voxel/kit/pane';
  import { PaneDivider } from '@voxel/kit/pane';

  import HistoryButtons from './HistoryButtons.svelte';
  import StageAxes from './StageAxes.svelte';

  interface Props {
    /** The instrument that the header offers to open while none is open. Null when none is selected. */
    instrumentId: string | null;
  }

  let { instrumentId }: Props = $props();

  const app = getVoxelStation();
  const previews = getPreviewContext();
  const preview = $derived(previews.current);

  const VIEWER_MODES: ViewerMode[] = ['fov', 'stage'];
  const viewerModeLabels: Record<ViewerMode, string> = { fov: 'FOV', stage: 'Stage' };
  const viewerMode = $derived(prefs.viewer.mode.get());
  // With no instrument open, the next one opens in the FOV view.
  $effect(() => {
    if (app.ready && !app.instrument) untrack(() => prefs.viewer.mode.set('fov'));
  });

  let stageViewport = $state.raw<Viewport | null>(null);
  $effect(() => {
    void app.instrument;
    stageViewport = null;
  });

  const PANEL_TABS: { id: CenterPanelTab; label: string }[] = [
    { id: 'frames', label: 'Frames' },
    { id: 'changes', label: 'Changes' },
    { id: 'issues', label: 'Issues' },
    { id: 'logs', label: 'Logs' }
  ];

  let panelRef = $state<Pane | undefined>(undefined);
  const panelOpen = $derived(panelRef ? !panelRef.isCollapsed() : true);
  const panelTab = $derived(prefs.centerPanel.tab.get());
  let viewerSplitEl = $state<HTMLElement | null>(null);
  const panel = createPaneSize(() => viewerSplitEl, {
    collapsed: 0,
    default: 22,
    fallback: { collapsed: 0, default: 35 },
    persist: 'center-panel'
  });
  const issueCount = $derived(issues.counts.errors + issues.counts.warnings);
  const changeCount = $derived(app.instrument ? propertyChanges(app.instrument).length : 0);
  const tabCounts: Partial<Record<CenterPanelTab, number>> = $derived({ issues: issueCount, changes: changeCount });
  // The Issues dot is red with an error, and yellow with only warnings.
  const dotColor: Partial<Record<CenterPanelTab, string>> = $derived({
    issues: LEVEL_DOT[issues.counts.errors > 0 ? 'error' : 'warning'],
    changes: 'bg-fg-muted'
  });

  /** "1 issue", "3 changes". */
  function countLabel(label: string, count: number): string {
    return `${count} ${(count === 1 ? label.slice(0, -1) : label).toLowerCase()}`;
  }

  function togglePanel() {
    if (panelRef) panel.toggle(panelRef);
  }

  /** Opens the panel on `tab`. A click on the tab that is open collapses the panel. */
  function pickTab(tab: CenterPanelTab) {
    const open = panelOpen && panelTab === tab;
    prefs.centerPanel.tab.set(tab);
    if (open || !panelOpen) togglePanel();
  }

  function openInstrument(): void {
    if (!instrumentId || !app.canOpen(instrumentId)) return;
    reportFailure(app.launch(instrumentId));
  }
</script>

<div class="app-bar gap-4 px-3">
  {#if app.instrument}
    <RadioBar
      value={viewerMode}
      options={VIEWER_MODES}
      formatLabel={(mode) => viewerModeLabels[mode]}
      onChange={(mode) => prefs.viewer.mode.set(mode)}
      size="md"
      aria-label="View"
      class="mr-auto"
    />
    <HistoryButtons />
  {:else if instrumentId && app.stationStatus !== 'closing'}
    <Button
      size="md"
      class="ml-auto"
      title={app.openBlocker(instrumentId) ?? 'Open instrument'}
      disabled={!app.canOpen(instrumentId)}
      onclick={openInstrument}
    >
      {#if app.instrumentTransition}
        <Spinner class="size-3.5" />
        Opening instrument…
      {:else}
        <Power />
        Open instrument
      {/if}
    </Button>
  {/if}
</div>
<div class="flex min-h-0 min-w-0 flex-col overflow-hidden">
  {#if app.instrument}
    {@const instrument = app.instrument}
    <div class="@container/viewer-pane flex h-full min-h-0 min-w-0 flex-col bg-canvas">
      <PaneGroup direction="vertical" bind:ref={viewerSplitEl} class="min-h-0 flex-1 bg-canvas">
        <Pane minSize={30} class="flex flex-1 flex-col justify-center">
          <div class="flex h-full flex-col bg-canvas">
            <div class="relative flex min-h-0 flex-1">
              <div class="relative min-w-0 flex-1 overflow-hidden" data-fly-origin>
                {#if viewerMode === 'stage'}
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
        <PaneDivider direction="horizontal" ondblclick={togglePanel} />
        <Pane bind:this={panelRef} {...panel} collapsible minSize={20} maxSize={55} class="min-h-0 bg-pane">
          <IssueViewer
            params={{ stationId: instrument.stationId, instrumentId: instrument.id }}
            class={cn(panelTab !== 'issues' && 'hidden')}
          />
          <PropertyChanges {instrument} class={cn(panelTab !== 'changes' && 'hidden')} />
          <PreviewFrameInfo
            previewer={preview}
            active={panelOpen && panelTab === 'frames'}
            class={cn(panelTab !== 'frames' && 'hidden')}
          />
          <LogViewer
            logs={app.logs}
            devices={[...instrument.devices.keys()]}
            expanded={panelOpen}
            showFooter={false}
            class={cn(panelTab !== 'logs' && 'hidden')}
          />
        </Pane>
      </PaneGroup>
      <footer
        class="grid min-h-pane-footer shrink-0 grid-cols-1 items-center gap-x-3 gap-y-2 border-t border-line-muted bg-shell px-3 py-2 @min-[64rem]/viewer-pane:grid-cols-[minmax(0,1fr)_auto]"
      >
        <div
          class="grid h-ui-sm auto-cols-fr grid-flow-col rounded-md border border-line-faint bg-element-bg p-px text-sm @min-[64rem]/viewer-pane:justify-self-start"
          role="group"
          aria-label="Bottom panel"
        >
          {#each PANEL_TABS as tab (tab.id)}
            {@const count = tabCounts[tab.id] ?? 0}
            <button
              type="button"
              title={count ? countLabel(tab.label, count) : undefined}
              aria-pressed={panelOpen && panelTab === tab.id}
              onclick={() => pickTab(tab.id)}
              class="flex cursor-pointer items-center justify-center gap-1 rounded-[calc(var(--radius-md)-1px)] px-2 whitespace-nowrap text-fg-muted transition-colors hover:text-fg focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus aria-pressed:bg-element-selected aria-pressed:text-fg"
            >
              <span class="size-1.5" aria-hidden="true"></span>
              {tab.label}
              <span class={cn('size-1.5 rounded-full', count ? dotColor[tab.id] : undefined)} aria-hidden="true"></span>
              {#if count}<span class="sr-only">, {countLabel(tab.label, count)}</span>{/if}
            </button>
          {/each}
        </div>
        <StageAxes stage={instrument.stage} />
      </footer>
    </div>
  {:else}
    <LogViewer logs={app.logs} />
  {/if}
</div>
