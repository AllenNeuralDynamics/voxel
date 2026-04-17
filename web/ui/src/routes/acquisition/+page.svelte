<script lang="ts">
  import { getSessionContext } from '$lib/context';
  import { Crosshair } from '$lib/icons';
  import { Button, PaneDivider, SpinBox, Select } from '$lib/kit';
  import MetadataPanel from '$lib/metadata/MetadataPanel.svelte';
  import ProgressGrid from '$lib/stacks/ProgressGrid.svelte';
  import StackSelector from '$lib/stacks/StackSelector.svelte';
  import { sanitizeString } from '$lib/utils';
  import { Pane, PaneGroup } from 'paneforge';
  import { toast } from 'svelte-sonner';

  const session = getSessionContext();

  const COMPRESSION_OPTIONS = [
    { value: 'blosc.lz4', label: 'blosc.lz4' },
    { value: 'blosc.zstd', label: 'blosc.zstd' },
    { value: 'zstd', label: 'zstd' },
    { value: 'lz4', label: 'lz4' },
    { value: 'gzip', label: 'gzip' },
    { value: 'none', label: 'none' }
  ];

  // ── Stack inspector ──

  const isAcquiring = $derived(session.mode === 'acquiring');
  const acquiringStack = $derived(session.stacks.list.find((s) => s.status === 'acquiring'));
  let followLive = $state(true);

  // Auto-select first stack if nothing is selected
  $effect(() => {
    if (session.stacks.selected.length === 0 && session.stacks.list.length > 0) {
      session.stacks.select([session.stacks.list[0]]);
    }
  });

  // Auto-follow: select the acquiring stack when followLive is on
  $effect(() => {
    if (followLive && acquiringStack) {
      session.stacks.select([acquiringStack]);
    }
  });

  const inspectedStack = $derived(session.stacks.selected[0] ?? null);

  // Break out of follow mode when user manually selects
  function onManualSelect() {
    if (isAcquiring) followLive = false;
  }

  function jumpToLive() {
    followLive = true;
  }

  // ── Acquisition start gating ──

  const hasPlanned = $derived(session.stacks.list.some((s) => s.status === 'planned'));

  // ── Clipboard ──

  async function copyDataPath() {
    const dataPath = session.details?.config?.info?.data_path;
    if (!dataPath) return;
    try {
      await navigator.clipboard.writeText(dataPath);
      toast.success('Copied to clipboard');
    } catch {
      toast.error('Failed to copy');
    }
  }
</script>

<div class="flex h-full flex-col overflow-hidden">
  <PaneGroup direction="horizontal" autoSaveId="acquire.content" class="min-h-0 flex-1 overflow-hidden">
    <!-- Left column: storage + metadata -->
    <Pane defaultSize={50} minSize={40} maxSize={60}>
      <div class="@container flex h-full flex-col overflow-hidden bg-canvas">
        <div class="flex flex-1 flex-col gap-4 overflow-y-auto p-4">
          <!-- Session info -->
          <section>
            <div class="grid grid-cols-1 gap-2 text-xs @sm:grid-cols-[10rem_1fr] @sm:items-center @sm:gap-x-3">
              <span class="text-fg-muted">Data Path</span>
              {#if session.details?.config?.info?.data_path}
                <button
                  onclick={copyDataPath}
                  class="cursor-pointer truncate text-start text-xs text-fg-muted transition-colors hover:text-fg"
                  title="Click to copy: {session.details.config.info.data_path}"
                >
                  {session.details.config.info.data_path}
                </button>
              {:else}
                <span class="text-fg-faint">—</span>
              {/if}
            </div>
          </section>

          <hr class="-mx-4 border-border" />

          <!-- Storage -->
          <section>
            <h3 class="mb-2 text-xs font-medium tracking-wide text-fg-muted/70 uppercase">Storage</h3>
            <div class="grid grid-cols-1 gap-2 text-xs @sm:grid-cols-[10rem_1fr] @sm:items-center @sm:gap-x-3">
              <span class="text-fg-muted">Compression</span>
              <Select
                value={session.output.compression ?? 'blosc.lz4'}
                options={COMPRESSION_OPTIONS}
                onchange={(v) => session.updateStorage({ compression: v })}
                size="xs"
              />
              <span class="text-fg-muted">Pyramid Level</span>
              <SpinBox
                value={session.output.max_level ?? 3}
                min={0}
                max={7}
                step={1}
                numCharacters={2}
                draggable={false}
                onChange={(v) => session.updateStorage({ max_level: v })}
                size="xs"
              />
            </div>
          </section>

          <hr class="-mx-4 border-border" />

          <!-- Metadata -->
          <MetadataPanel {session} />
        </div>
      </div>
    </Pane>

    <PaneDivider direction="vertical" />

    <!-- Right column: stack inspector -->
    <Pane class="flex h-full flex-col overflow-hidden">
      <!-- Stack selector -->
      <div class="flex items-center gap-2 px-4 pt-3 pb-2">
        <div class="min-w-0 flex-1" onclick={onManualSelect} onkeydown={onManualSelect} role="presentation">
          <StackSelector stacks={session.stacks} size="sm" class="w-full" />
        </div>
        <button
          class="cursor-pointer rounded bg-transparent p-1 transition-colors
            {isAcquiring && !followLive ? 'text-info hover:text-info/80' : 'text-fg-faint'}"
          title="Follow active stack"
          disabled={!isAcquiring || followLive}
          onclick={jumpToLive}
        >
          <Crosshair width="14" height="14" />
        </button>
      </div>

      <!-- Stack details -->
      <div class="flex flex-1 flex-col gap-4 overflow-y-auto px-4 pt-1 pb-4">
        {#if inspectedStack}
          <div class="grid grid-cols-[8rem_1fr] gap-x-3 gap-y-1.5 text-xs">
            <span class="text-fg-muted">Profile</span>
            <span class="text-fg">{sanitizeString(inspectedStack.profile_id)}</span>

            <span class="text-fg-muted">Position</span>
            <span class="text-fg tabular-nums">
              ({(inspectedStack.x / 1000).toFixed(4)}, {(inspectedStack.y / 1000).toFixed(4)}) mm
            </span>

            <span class="text-fg-muted">Z Range</span>
            <span class="text-fg tabular-nums">
              {(inspectedStack.z_start / 1000).toFixed(3)} → {(inspectedStack.z_end / 1000).toFixed(3)} mm
            </span>

            <span class="text-fg-muted">Frames</span>
            <span class="text-fg tabular-nums">{inspectedStack.num_frames}</span>

            <span class="text-fg-muted">Status</span>
            <span class="text-fg" data-stack-status={inspectedStack.status}>
              <span class="text-(--stack-status)">{inspectedStack.status}</span>
            </span>

            <span class="text-fg-muted">Created</span>
            <span class="text-fg-faint tabular-nums">{new Date(inspectedStack.created_at).toLocaleString()}</span>

            {#if inspectedStack.edited_at}
              <span class="text-fg-muted">Edited</span>
              <span class="text-fg-faint tabular-nums">{new Date(inspectedStack.edited_at).toLocaleString()}</span>
            {/if}

            {#if inspectedStack.started_at}
              <span class="text-fg-muted">Started</span>
              <span class="text-fg-faint tabular-nums">{new Date(inspectedStack.started_at).toLocaleString()}</span>
            {/if}

            {#if inspectedStack.completed_at}
              <span class="text-fg-muted">Completed</span>
              <span class="text-fg-faint tabular-nums">{new Date(inspectedStack.completed_at).toLocaleString()}</span>
            {/if}

            {#if inspectedStack.skipped_at}
              <span class="text-fg-muted">Skipped</span>
              <span class="text-fg-faint tabular-nums">{new Date(inspectedStack.skipped_at).toLocaleString()}</span>
            {/if}

            {#if inspectedStack.started_at && inspectedStack.completed_at}
              {@const durationMs =
                new Date(inspectedStack.completed_at).getTime() - new Date(inspectedStack.started_at).getTime()}
              <span class="text-fg-muted">Duration</span>
              <span class="text-fg-faint tabular-nums">
                {durationMs >= 60000
                  ? `${Math.floor(durationMs / 60000)}m ${Math.round((durationMs % 60000) / 1000)}s`
                  : `${(durationMs / 1000).toFixed(1)}s`}
              </span>
            {/if}
          </div>

          {#if inspectedStack.status === 'acquiring' || inspectedStack.status === 'completed'}
            <hr class="border-border" />
            <div class="space-y-2">
              <h4 class="text-xs font-medium text-fg-muted">Channels</h4>
              <p class="text-xs text-fg-faint">Channel details will appear here during acquisition.</p>
            </div>
          {/if}
        {:else}
          <div class="flex flex-1 items-center justify-center">
            <p class="text-sm text-fg-faint">No stacks configured</p>
          </div>
        {/if}
      </div>
    </Pane>
  </PaneGroup>

  <!-- Full-width footer: progress + action -->
  <div class="flex flex-col gap-3 border-t border-border px-4 py-3 pb-6">
    {#if !hasPlanned && !isAcquiring}
      <Button size="sm" variant="outline" disabled class="w-full">Add new stacks to start acquisition</Button>
    {:else}
      <Button
        size="sm"
        variant={isAcquiring ? 'outline' : 'default'}
        onclick={() => (isAcquiring ? session.acquisition.stop() : session.acquisition.start())}
        class="w-full {isAcquiring ? 'border-danger text-danger hover:bg-danger/10' : ''}"
      >
        {isAcquiring ? 'Stop Acquisition' : 'Start Acquisition'}
      </Button>
    {/if}
    <div onclick={onManualSelect} onkeydown={onManualSelect} role="presentation">
      <ProgressGrid stacks={session.stacks} acquisition={session.acquisition} />
    </div>
  </div>
</div>

<style>
  /* DnD animation overrides */
  :global(.profile-chip.svelte-dnd-dragging) {
    opacity: 0.4;
    transform: scale(0.95);
  }

  :global(.profile-chip.svelte-dnd-drop-target) {
    outline: none;
    box-shadow: 0 0 0 2px var(--color-info);
    transform: scale(1.05);
  }
</style>
