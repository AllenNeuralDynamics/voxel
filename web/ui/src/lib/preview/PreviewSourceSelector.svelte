<script lang="ts">
  import { Select } from 'bits-ui';

  import { Check, ChevronDown, Crosshair, DotsSpinner, ImageLight, TrashCanOutline, VideoCamera } from '$lib/icons';
  import { Button } from '$lib/kit';
  import { getVoxelApp } from '$lib/model';
  import { toastError } from '$lib/utils';

  const app = getVoxelApp();
  const instrument = $derived(app.instrument);
  const snaps = app.snaps;

  const canSnap = $derived(!!instrument && !app.snapping);

  const LIVE = 'live';

  /** Current source as a Select value: a snapshot id, or the `live` sentinel. */
  const currentValue = $derived(snaps.active?.id ?? LIVE);

  /** Typeahead / a11y labels for the primitive. */
  const items = $derived([
    { value: LIVE, label: 'Live' },
    ...snaps.list.map((s) => ({ value: s.id, label: s.label }))
  ]);

  function changeSource(v: string) {
    snaps.view(v === LIVE ? null : v);
  }

  function posLabel(x: number, y: number, z: number): string {
    return `${(x / 1000).toFixed(3)}, ${(y / 1000).toFixed(3)}, ${(z / 1000).toFixed(3)}`;
  }

  const itemClass =
    'group flex w-full cursor-pointer items-center gap-2 rounded-sm px-1.5 py-1.5 text-sm outline-none select-none data-highlighted:bg-floating';
</script>

<div class="flex items-center gap-2">
  <Select.Root type="single" value={currentValue} onValueChange={changeSource} {items}>
    <Select.Trigger
      data-fly-target
      class="flex h-ui-md w-72 items-center gap-2 rounded-sm border border-input bg-element-bg px-2 text-sm transition-colors hover:bg-element-hover focus:border-focused focus:outline-none"
    >
      {#if snaps.active}
        <img
          src={snaps.active.thumbnail}
          alt=""
          class="h-5 w-7 shrink-0 rounded-sm border border-border object-cover"
        />
        <span class="truncate">{snaps.active.label}</span>
      {:else}
        <VideoCamera width="16" height="16" class="shrink-0 text-fg-muted" />
        <span>Live</span>
      {/if}
      <ChevronDown width="14" height="14" class="ml-auto shrink-0 opacity-50" />
    </Select.Trigger>

    <Select.Portal>
      <Select.Content
        side="bottom"
        align="start"
        sideOffset={4}
        class="z-50 w-72 rounded-sm border border-border bg-surface p-1 text-fg shadow-lg outline-none"
      >
        <Select.Viewport class="max-h-(--bits-select-content-available-height) overflow-y-auto">
          <!-- Live (pinned) -->
          <Select.Item value={LIVE} label="Live" class={itemClass}>
            {#snippet children({ selected })}
              <VideoCamera width="16" height="16" class="shrink-0 text-fg-muted" />
              <span class="flex-1 truncate">Live</span>
              {#if selected}<Check width="14" height="14" class="shrink-0 text-primary" />{/if}
            {/snippet}
          </Select.Item>

          {#if snaps.size > 0}
            <div class="my-1 border-t border-border"></div>
          {/if}

          {#each snaps.list as snap (snap.id)}
            <Select.Item value={snap.id} label={snap.label} class={itemClass}>
              {#snippet children({ selected })}
                <img
                  src={snap.thumbnail}
                  alt=""
                  class="h-9 w-11 shrink-0 rounded border border-border object-cover"
                />
                <div class="flex min-w-0 flex-1 flex-col gap-1 justify-between">
                  <div class="flex min-w-0 justify-between items-center gap-1.5">
                    <span class="min-w-0 truncate">{snap.label}</span>
                    {#if snap.profileLabel}
                        <span class="shrink-0 truncate max-w-[10ch] rounded bg-element-bg px-1 py-0.5 text-xs text-fg-muted">
                          {snap.profileLabel}
                        </span>

                    {/if}
                  </div>
                  <span class="truncate font-mono text-xs text-fg-muted tabular-nums">
                    {posLabel(snap.stageX, snap.stageY, snap.stageZ)}
                  </span>
                </div>
                {#if selected}<Check width="14" height="14" class="shrink-0 text-primary" />{/if}
                <div class="flex shrink-0 flex-col justify-between">
                  <Button
                    variant="ghost"
                    size="icon-xs"
                    title="Go to position"
                    class="hover:bg-transparent hover:text-primary-soft"
                    onpointerdown={(e) => e.stopPropagation()}
                    onpointerup={(e) => e.stopPropagation()}
                    onclick={(e) => {
                      e.stopPropagation();
                      e.preventDefault();
                      toastError(instrument?.moveStage({ x: snap.stageX, y: snap.stageY, z: snap.stageZ }));
                    }}
                  >
                    <Crosshair width="13" height="13" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-xs"
                    title="Delete snapshot"
                    class="opacity-0 transition group-hover:opacity-100 hover:bg-transparent hover:text-danger"
                    onpointerdown={(e) => e.stopPropagation()}
                    onpointerup={(e) => e.stopPropagation()}
                    onclick={(e) => {
                      e.stopPropagation();
                      e.preventDefault();
                      snaps.remove(snap.id);
                    }}
                  >
                    <TrashCanOutline width="13" height="13" />
                  </Button>
                </div>
              {/snippet}
            </Select.Item>
          {/each}
        </Select.Viewport>
      </Select.Content>
    </Select.Portal>
  </Select.Root>

  <Button
    variant="secondary"
    size="md"
    disabled={!canSnap}
    title={app.snapping ? 'Snapping…' : 'Capture snapshot'}
    class="text-sm"
    onclick={() => toastError(app.captureSnapshot())}
  >
    {#if app.snapping}
      <DotsSpinner width="16" height="16" />
    {:else}
      <ImageLight width="16" height="16" />
    {/if}
    Snap
  </Button>
</div>
