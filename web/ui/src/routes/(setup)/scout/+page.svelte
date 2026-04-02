<script lang="ts">
  import { getSessionContext } from '$lib/context';
  import type { Snapshot } from '$lib/main/snapshots.svelte';
  import { Button, ContextMenu, Rename } from '$lib/ui/kit';
  import { Pane, PaneGroup } from 'paneforge';
  import PaneDivider from '$lib/ui/kit/PaneDivider.svelte';
  import { cn } from '$lib/utils';
  import { Crosshair, TrashCanOutline, ImageLight } from '$lib/icons';
  import { ElementSize } from 'runed';

  const session = getSessionContext();
  const snaps = $derived(session.snaps);

  let renamingId = $state<string | null>(null);

  let canSnap = $derived(session.preview.isPreviewing || session.mode === 'acquiring');

  let previewUrl = $state<string | null>(null);
  let previewAspect = $state('');
  let prevBlobRef: Blob | null = null;

  let channelEntries = $derived(Object.entries(snaps.focused?.channels ?? {}));

  $effect(() => {
    const focused = snaps.focused;
    if (focused && focused.blob !== prevBlobRef) {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      previewUrl = URL.createObjectURL(focused.blob);
      prevBlobRef = focused.blob;
    } else if (!focused) {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      previewUrl = null;
      previewAspect = '';
      prevBlobRef = null;
    }
  });

  function handleClick(e: MouseEvent, id: string) {
    if (e.ctrlKey || e.metaKey) {
      snaps.sel.toggle(id);
    } else if (e.shiftKey) {
      snaps.sel.rangeSelect(id);
    } else {
      snaps.sel.select(id);
    }
  }

  function handleKeydown(e: KeyboardEvent, id: string) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      snaps.sel.select(id);
    }
  }

  const SIDEBAR_MIN_PX = 300;
  let paneGroupEl = $state<HTMLElement | null>(null);
  const paneGroupSize = new ElementSize(() => paneGroupEl);
</script>

{#snippet snapItem(snap: Snapshot)}
  {@const isSelected = snaps.sel.has(snap.id)}
  {@const snapPos = { x: snap.stageX, y: snap.stageY }}
  {@const snapPosMm = { x: snap.stageX / 1000, y: snap.stageY / 1000 }}
  <ContextMenu.Root>
    <ContextMenu.Trigger>
      <div
        role="option"
        tabindex="0"
        aria-selected={isSelected}
        class={cn(
          'flex w-full cursor-pointer items-start gap-2.5 px-3 py-2 text-left transition-colors outline-none select-none',
          snaps.sel.focused === snap.id
            ? 'bg-element-selected'
            : isSelected
              ? 'bg-element-hover'
              : 'hover:bg-element-hover focus-visible:bg-element-hover'
        )}
        onclick={(e) => handleClick(e, snap.id)}
        onkeydown={(e) => handleKeydown(e, snap.id)}
      >
        <!-- Thumbnail -->
        <img
          src={snap.thumbnail}
          alt={snap.label}
          class="h-12 w-16 shrink-0 rounded border border-border object-cover"
        />

        <!-- Info -->
        <div class="flex min-w-0 flex-1 flex-col gap-0.5">
          <Rename
            value={snap.label}
            size="sm"
            class="text-fg"
            textClass="truncate"
            mode={renamingId === snap.id ? 'edit' : 'view'}
            onSave={(newLabel) => {
              snaps.rename(snap.id, newLabel);
              renamingId = null;
            }}
            onCancel={() => (renamingId = null)}
          />
          <span class="font-mono text-xs text-fg-muted tabular-nums">
            {snapPosMm.x.toFixed(3)}, {snapPosMm.y.toFixed(3)}, {(snap.stageZ / 1000).toFixed(3)}
          </span>
        </div>

        <!-- Profile badge -->
        {#if snap.profileLabel}
          <span class="shrink-0 rounded bg-element-bg px-1.5 py-0.5 text-xs text-fg-muted">{snap.profileLabel}</span>
        {/if}
      </div>
    </ContextMenu.Trigger>
    <ContextMenu.Content>
      <ContextMenu.Item
        onSelect={() => {
          session.stage.moveXY(snapPos.x, snapPos.y);
          session.stage.moveZ(snap.stageZ);
        }}
      >
        Go to position
      </ContextMenu.Item>
      <ContextMenu.Item onSelect={() => (renamingId = snap.id)}>Rename</ContextMenu.Item>
      <ContextMenu.Separator />
      <ContextMenu.Sub>
        <ContextMenu.SubTrigger disabled={!session.gridEditable}>Align grid</ContextMenu.SubTrigger>
        <ContextMenu.SubContent>
          <ContextMenu.Item onSelect={() => session.alignGrid('top', snapPos)}>Top</ContextMenu.Item>
          <ContextMenu.Item onSelect={() => session.alignGrid('bottom', snapPos)}>Bottom</ContextMenu.Item>
          <ContextMenu.Item onSelect={() => session.alignGrid('left', snapPos)}>Left</ContextMenu.Item>
          <ContextMenu.Item onSelect={() => session.alignGrid('right', snapPos)}>Right</ContextMenu.Item>
          <ContextMenu.Separator />
          <ContextMenu.Item onSelect={() => session.alignGrid('center', snapPos)}>Center</ContextMenu.Item>
        </ContextMenu.SubContent>
      </ContextMenu.Sub>
      <ContextMenu.Separator />
      <ContextMenu.Item variant="destructive" onSelect={() => snaps.remove(snap.id)}>Delete</ContextMenu.Item>
    </ContextMenu.Content>
  </ContextMenu.Root>
{/snippet}

<PaneGroup bind:ref={paneGroupEl} direction="horizontal" autoSaveId="setup.scout" class="h-full">
  <Pane defaultSize={70} minSize={40}>
    <div class="flex h-full flex-col overflow-hidden bg-canvas">
      {#if snaps.focused && previewUrl}
        <div class="flex h-full items-center justify-center overflow-hidden">
          <div class="relative max-h-full max-w-full" style:aspect-ratio={previewAspect}>
            <img
              src={previewUrl}
              alt={snaps.focused.label}
              class="h-full w-full"
              onload={(e) => {
                const img = e.currentTarget as HTMLImageElement;
                previewAspect = `${img.naturalWidth} / ${img.naturalHeight}`;
              }}
            />
            <div class="absolute bottom-1 left-1 rounded-sm bg-surface/10 text-xs backdrop-blur-xs">
              {#if channelEntries.length > 0}
                {@const hasExposure = channelEntries.some(([, ch]) => ch.detection?.exposureTime != null)}
                {@const hasBinning = channelEntries.some(([, ch]) => ch.detection?.binning != null)}
                {@const hasPower = channelEntries.some(([, ch]) => ch.illumination?.powerSetpoint != null)}
                {@const propCount = 1 + (hasExposure ? 1 : 0) + (hasBinning ? 1 : 0) + (hasPower ? 1 : 0)}
                <!-- <div class="border-t border-border"></div> -->
                <div
                  class="grid items-center gap-x-3 gap-y-0 px-2 py-1"
                  style:grid-template-columns="auto repeat({propCount}, auto)"
                >
                  <!-- Header row -->
                  <span class="text-fg-faint">Chan.</span>
                  <span class="text-fg-faint">Lvl.</span>
                  {#if hasExposure}<span class="text-fg-faint">Exp.</span>{/if}
                  {#if hasBinning}<span class="text-fg-faint">Bin.</span>{/if}
                  {#if hasPower}<span class="text-fg-faint">Pwr.</span>{/if}

                  <!-- Channel rows -->
                  {#each channelEntries as [name, ch] (name)}
                    {@const color = session.preview.resolveColor(ch.colormap) ?? 'var(--color-fg-muted)'}
                    <div class="flex items-center gap-1.5">
                      <span class="h-2 w-2 shrink-0 rounded-full" style:background-color={color}></span>
                      <span class="font-medium text-fg">{ch.label}</span>
                    </div>
                    <span class="text-fg-muted">
                      {(ch.levelsMin * 100).toFixed(0)}–{(ch.levelsMax * 100).toFixed(0)}%
                    </span>
                    {#if hasExposure}
                      <span class="text-fg-muted">
                        {ch.detection?.exposureTime != null ? `${ch.detection.exposureTime} ms` : '–'}
                      </span>
                    {/if}
                    {#if hasBinning}
                      <span class="text-fg-muted">
                        {ch.detection?.binning != null ? `${ch.detection.binning}x` : '–'}
                      </span>
                    {/if}
                    {#if hasPower}
                      <span class="text-fg-muted">
                        {ch.illumination?.powerSetpoint != null
                          ? `${ch.illumination.powerSetpoint.toFixed(1)} mW`
                          : '–'}
                      </span>
                    {/if}
                  {/each}
                </div>
              {/if}
            </div>
          </div>
        </div>
      {:else}
        <div class="flex h-full flex-col items-center justify-center gap-3 text-fg-faint">
          <Crosshair width="32" height="32" class="opacity-40" />
          <p class="text-sm">Move the stage and capture snapshots to explore your sample</p>
          <Button variant="outline" size="sm" disabled={!canSnap} onclick={() => session.snap()}>
            <ImageLight width="14" height="14" />
            Capture Snapshot
          </Button>
          {#if !canSnap}
            <span class="text-xs text-fg-faint">Start preview to capture snapshots</span>
          {/if}
        </div>
      {/if}
    </div>
  </Pane>

  <PaneDivider direction="vertical" />

  <Pane
    defaultSize={30}
    minSize={paneGroupSize.width > 0 ? (SIDEBAR_MIN_PX / paneGroupSize.width) * 100 : 25}
    maxSize={45}
  >
    <div class="flex h-full flex-col overflow-hidden">
      <!-- Header with capture button -->
      <div class="flex items-center justify-between border-b border-border px-3 py-2">
        <span class="text-xs text-fg-muted">
          {snaps.size} snapshot{snaps.size !== 1 ? 's' : ''}
        </span>
        <div class="flex items-center gap-1" title={canSnap ? undefined : 'Start preview to capture snapshots'}>
          {#if snaps.size > 0}
            <Button
              variant="ghost"
              size="xs"
              class="text-fg-muted hover:bg-danger/10 hover:text-danger"
              onclick={() => {
                if (snaps.sel.size > 1) {
                  snaps.remove(snaps.sel.selection);
                } else {
                  snaps.clear();
                }
              }}
            >
              <TrashCanOutline width="14" height="14" />
              {snaps.sel.size > 1 ? `Clear ${snaps.sel.size}` : 'Clear all'}
            </Button>
          {/if}
          <Button variant="outline" size="xs" disabled={!canSnap} onclick={() => session.snap()}>
            <ImageLight width="14" height="14" />
            Snap
          </Button>
        </div>
      </div>

      <div class="flex-1 overflow-y-auto" role="listbox" aria-label="Snapshots" aria-multiselectable="true">
        {#if snaps.size === 0}
          <div class="flex h-full items-center justify-center p-4">
            <p class="text-center text-sm text-fg-faint">No snapshots yet</p>
          </div>
        {:else}
          <div class="space-y-px">
            {#each snaps.list as snap (snap.id)}
              {@render snapItem(snap)}
            {/each}
          </div>
        {/if}
      </div>
    </div>
  </Pane>
</PaneGroup>
