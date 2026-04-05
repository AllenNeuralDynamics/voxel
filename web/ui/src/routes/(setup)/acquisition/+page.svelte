<script lang="ts">
  import { getSessionContext } from '$lib/context';
  import { Crosshair } from '$lib/icons';
  import { Button, PaneDivider, SpinBox, Select } from '$lib/ui/kit';
  import MetadataPanel from '$lib/ui/MetadataPanel.svelte';
  import StackSelector from '$lib/ui/StackSelector.svelte';
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
  const acquiringStack = $derived(session.stacks.find((s) => s.status === 'acquiring'));
  let followLive = $state(true);

  // Auto-select first stack if nothing is selected
  $effect(() => {
    if (session.selectedStacks.length === 0 && session.stacks.length > 0) {
      session.selectStacks([session.stacks[0]]);
    }
  });

  // Auto-follow: select the acquiring stack when followLive is on
  $effect(() => {
    if (followLive && acquiringStack) {
      session.selectStacks([acquiringStack]);
    }
  });

  const inspectedStack = $derived(session.selectedStacks[0] ?? null);

  // Break out of follow mode when user manually selects
  function onManualSelect() {
    if (isAcquiring) followLive = false;
  }

  function jumpToLive() {
    followLive = true;
  }

  // ── Acquisition progress ──

  const stackCounts = $derived.by(() => {
    let planned = 0;
    let completed = 0;
    let failed = 0;
    let acquiring = 0;
    for (const s of session.stacks) {
      if (s.status === 'planned') planned++;
      else if (s.status === 'completed') completed++;
      else if (s.status === 'failed') failed++;
      else if (s.status === 'acquiring') acquiring++;
    }
    return { planned, completed, failed, acquiring, total: session.stacks.length };
  });

  const progressFraction = $derived(
    stackCounts.total > 0 ? (stackCounts.completed + stackCounts.failed) / stackCounts.total : 0
  );

  // ── Clipboard ──

  async function copySessionDir() {
    if (!session.info?.session_dir) return;
    try {
      await navigator.clipboard.writeText(session.info.session_dir);
      toast.success('Copied to clipboard');
    } catch {
      toast.error('Failed to copy');
    }
  }
</script>

<PaneGroup direction="horizontal" autoSaveId="acquire.content" class="h-full overflow-hidden">
  <!-- Left column: storage + metadata -->
  <Pane defaultSize={50} minSize={40} maxSize={60}>
    <div class="@container flex h-full flex-col overflow-hidden bg-canvas">
      <div class="flex flex-1 flex-col gap-4 overflow-y-auto p-4">
        <!-- Session info -->
        <section>
          <div class="grid grid-cols-1 gap-2 text-xs @sm:grid-cols-[10rem_1fr] @sm:items-center @sm:gap-x-3">
            <span class="text-fg-muted">Directory</span>
            {#if session.info?.session_dir}
              <button
                onclick={copySessionDir}
                class="cursor-pointer truncate text-start text-xs text-fg-muted transition-colors hover:text-fg"
                title="Click to copy: {session.info.session_dir}"
              >
                {session.info.session_dir}
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
            <!-- TODO: Store path editing — needs multiline or path picker for long paths -->
            <!-- <span class="text-fg-muted">Store Path</span>
            <TextInput
              value={session.storage.store_path ?? ''}
              placeholder="/path/to/zarr"
              align="left"
              onChange={(v) => session.updateStorage({ store_path: v || null })}
              size="xs"
            /> -->
            <span class="text-fg-muted">Compression</span>
            <Select
              value={session.storage.compression ?? 'blosc.lz4'}
              options={COMPRESSION_OPTIONS}
              onchange={(v) => session.updateStorage({ compression: v })}
              size="xs"
            />
            <span class="text-fg-muted">Pyramid Level</span>
            <SpinBox
              value={session.storage.max_level ?? 3}
              min={0}
              max={7}
              step={1}
              numCharacters={2}
              draggable={false}
              onChange={(v) => session.updateStorage({ max_level: v })}
              size="xs"
            />
            <span class="text-fg-muted">Shard Size</span>
            <SpinBox
              value={session.storage.target_shard_gb ?? 1}
              min={0.1}
              max={10}
              step={0.5}
              decimals={1}
              suffix="GB"
              onChange={(v) => session.updateStorage({ target_shard_gb: v })}
              size="xs"
            />
            <span class="text-fg-muted">Batch Z Shards</span>
            <div class="flex items-center gap-1.5">
              <SpinBox
                value={session.storage.batch_z_shards ?? 1}
                min={1}
                max={16}
                step={1}
                numCharacters={3}
                draggable={false}
                onChange={(v) => session.updateStorage({ batch_z_shards: v })}
                size="xs"
              />
              <span class="text-fg-faint">
                = {(session.storage.batch_z_shards ?? 1) * (1 << (session.storage.max_level ?? 3))} frames
              </span>
            </div>
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
        <StackSelector {session} size="sm" class="w-full" />
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
        </div>

        <!-- Per-channel details (placeholder — will be populated from acquisition progress events) -->
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

    <!-- Acquisition progress + start -->
    <div class="flex flex-col gap-3 border-t border-border px-4 py-3">
      {#if stackCounts.total > 0}
        <div class="space-y-1.5">
          <div class="flex items-center justify-between text-xs text-fg-muted">
            <span>
              {stackCounts.completed + stackCounts.failed}/{stackCounts.total} stacks
            </span>
            {#if stackCounts.failed > 0}
              <span class="text-danger">{stackCounts.failed} failed</span>
            {/if}
          </div>
          <div class="h-1.5 w-full overflow-hidden rounded-full bg-border">
            <div class="h-full rounded-full bg-info transition-[width]" style="width: {progressFraction * 100}%"></div>
          </div>
        </div>
      {/if}
      {#if stackCounts.planned === 0 && !isAcquiring}
        <Button size="sm" variant="outline" disabled class="w-full">Add new stacks to start acquisition</Button>
      {:else}
        <Button
          size="sm"
          variant={isAcquiring ? 'outline' : 'default'}
          onclick={() => (isAcquiring ? session.stopAcquisition() : session.startAcquisition())}
          class="w-full {isAcquiring ? 'border-danger text-danger hover:bg-danger/10' : ''}"
        >
          {isAcquiring ? 'Stop Acquisition' : 'Start Acquisition'}
        </Button>
      {/if}
    </div>
  </Pane>
</PaneGroup>

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
