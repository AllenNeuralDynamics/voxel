<script lang="ts">
  import { getSessionContext } from '$lib/context';
  import { Button, Checkbox, Dialog, Select, SpinBox } from '$lib/ui/kit';
  import { Pane, PaneGroup } from 'paneforge';
  import PaneDivider from '$lib/ui/kit/PaneDivider.svelte';
  import { sanitizeString } from '$lib/utils';
  import { cn } from '$lib/utils';
  import {
    TrashCanOutline,
    Restore,
    LucideCircle,
    Check,
    AlertCircleOutline,
    Minus,
    DotsSpinner
  } from '$lib/icons';
  import { watch, ElementSize } from 'runed';
  import type { Stack, StackStatus } from '$lib/main/types';

  const session = getSessionContext();

  // --- Filter ---

  type StackFilter = 'all' | StackStatus;
  let filter = $state<StackFilter>('all');

  const filterOptions: { value: StackFilter; label: string }[] = [
    { value: 'all', label: 'All Stacks' },
    { value: 'planned', label: 'Planned' },
    { value: 'completed', label: 'Completed' },
    { value: 'failed', label: 'Failed' },
    { value: 'skipped', label: 'Skipped' }
  ];

  // --- Derived data ---

  const filteredStacks = $derived.by(() => {
    if (filter === 'all') return session.activeStacks;
    return session.activeStacks.filter((s) => s.status === filter);
  });

  const hasSelection = $derived(session.selectedStacks.length > 0);

  // Acquisition order: index of each stack in the plan's ordered stacks list
  const acquisitionOrder = $derived(
    new Map(session.stacks.map((s, i) => [`${s.profile_id}:${s.row},${s.col}`, i + 1]))
  );

  // --- Merged Z values for batch editing ---

  function commonValue(values: number[]): number | undefined {
    if (values.length === 0) return undefined;
    const first = values[0];
    return values.every((v) => v === first) ? first : undefined;
  }

  const selectedStacks = $derived(session.selectedStacks);

  const commonZStart = $derived(commonValue(selectedStacks.map((s) => s.z_start)));
  const commonZEnd = $derived(commonValue(selectedStacks.map((s) => s.z_end)));
  const commonZStep = $derived(commonValue(selectedStacks.map((s) => s.z_step)));
  const totalFrames = $derived(selectedStacks.reduce((sum, s) => sum + s.num_frames, 0));
  const totalRange = $derived(selectedStacks.reduce((sum, s) => sum + Math.abs(s.z_end - s.z_start), 0));

  // --- Actions ---

  function applyZRange(field: 'zStartUm' | 'zEndUm', value: number) {
    if (selectedStacks.length === 0) return;
    session.editStacks(
      selectedStacks.map((s) => ({
        row: s.row,
        col: s.col,
        zStartUm: field === 'zStartUm' ? value : s.z_start,
        zEndUm: field === 'zEndUm' ? value : s.z_end
      }))
    );
  }

  function removeSelectedStacks() {
    const stacks = session.selectedStacks;
    if (stacks.length === 0) return;
    session.removeStacks(stacks.map((s) => ({ row: s.row, col: s.col })));
    clearDialogOpen = false;
  }

  // --- Selection ---

  let lastClickedIndex = $state<number>(-1);

  function handleRowClick(stack: Stack, index: number, e: MouseEvent) {
    const pos = { row: stack.row, col: stack.col };
    if (e.metaKey || e.ctrlKey) {
      if (session.isStackSelected(stack.row, stack.col)) {
        session.removeStacksFromSelection([pos]);
      } else {
        session.addStacksToSelection([pos]);
      }
    } else if (e.shiftKey && lastClickedIndex >= 0) {
      const from = Math.min(lastClickedIndex, index);
      const to = Math.max(lastClickedIndex, index);
      const range = filteredStacks.slice(from, to + 1);
      session.selectStacks(range);
    } else {
      session.selectStacks([pos]);
    }
    lastClickedIndex = index;
  }

  function toggleStack(stack: Stack) {
    const pos = { row: stack.row, col: stack.col };
    if (session.isStackSelected(stack.row, stack.col)) {
      session.removeStacksFromSelection([pos]);
    } else {
      session.addStacksToSelection([pos]);
    }
  }

  // --- Auto-scroll to selection from canvas ---

  watch(
    () => session.selectedStacks[0],
    (first) => {
      if (!first) return;
      const el = document.getElementById(`stack-${first.row}-${first.col}`);
      el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  );

  // --- Clear dialog ---

  let clearDialogOpen = $state(false);
  let clearMode = $state<'selected' | 'all'>('selected');

  // --- Profile info ---

  const activeProfile = $derived(session.config.profiles[session.activeProfileId ?? '']);

  const activeProfileLabel = $derived(
    session.activeProfileId ? (activeProfile?.label ?? sanitizeString(session.activeProfileId)) : ''
  );

  const stackCount = $derived(session.activeStacks.length);

  // --- Pane sizing (pixel-based min for sidebar) ---

  const SIDEBAR_MIN_PX = 300;
  let paneGroupEl = $state<HTMLElement | null>(null);
  const paneGroupSize = new ElementSize(() => paneGroupEl);
</script>

{#snippet statusIcon(status: StackStatus)}
  {#if status === 'acquiring'}
    <DotsSpinner width="12" height="12" class="text-(--stack-status)" />
  {:else if status === 'completed'}
    <Check width="12" height="12" class="text-(--stack-status)" />
  {:else if status === 'failed'}
    <AlertCircleOutline width="12" height="12" class="text-(--stack-status)" />
  {:else if status === 'skipped'}
    <Minus width="12" height="12" class="text-(--stack-status)" />
  {:else}
    <LucideCircle width="12" height="12" class="text-(--stack-status)" />
  {/if}
{/snippet}

{#snippet stackRow(stack: Stack, selected: boolean, index: number)}
  <div
    id="stack-{stack.row}-{stack.col}"
    role="row"
    tabindex="0"
    aria-selected={selected}
    aria-label="Stack at ({(stack.x / 1000).toFixed(2)}, {(stack.y / 1000).toFixed(2)}) mm, {stack.status}"
    data-stack-status={stack.status}
    class={cn(
      'col-span-full grid cursor-default grid-cols-subgrid items-center gap-x-3 px-3 py-1.5 text-left text-xs transition-colors',
      'border-b border-border/50 last:border-b-0',
      selected ? 'bg-element-selected' : 'hover:bg-element-hover'
    )}
    onclick={(e) => handleRowClick(stack, index, e)}
    onkeydown={(e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        handleRowClick(stack, index, e as unknown as MouseEvent);
      }
    }}
  >
    <!-- Checkbox -->
    <Checkbox checked={selected} size="sm" onchange={() => toggleStack(stack)} />

    <!-- X position (mm) -->
    <span class="text-fg-muted tabular-nums">{(stack.x / 1000).toFixed(4)}</span>
    <!-- Y position (mm) -->
    <span class="text-fg-muted tabular-nums">{(stack.y / 1000).toFixed(4)}</span>

    <!-- Z range -->
    <div class="pr-1">
      <span class="text-fg tabular-nums">
        {(stack.z_start / 1000).toFixed(3)} → {(stack.z_end / 1000).toFixed(3)} mm
      </span>
    </div>

    <!-- Frame count -->
    <div class="pr-2">
      <span class="text-fg-muted tabular-nums">{stack.num_frames} frames</span>
    </div>

    <!-- Acquisition order -->
    {#if true}
      {@const order = acquisitionOrder.get(`${stack.profile_id}:${stack.row},${stack.col}`)}
      <span class="justify-self-end text-fg-faint tabular-nums">#{order ?? '?'}</span>
    {/if}

    <!-- Status -->
    <span class="flex items-center justify-self-end">
      {@render statusIcon(stack.status)}
    </span>
  </div>
{/snippet}

<PaneGroup bind:ref={paneGroupEl} direction="horizontal" autoSaveId="setup.plan" class="h-full">
  <!-- Stack list (main area) -->
  <Pane minSize={40}>
    <div class="flex h-full flex-col overflow-hidden pb-2">
      <!-- List header -->
      <div class="flex items-center gap-2 border-b border-border px-3 py-2">
        <div class="flex min-w-0 flex-1 items-center gap-2">
          {#if activeProfile}
            <span class="truncate text-sm text-fg">{activeProfileLabel}</span>
            <span class="text-xs text-fg-muted">
              {filteredStacks.length} stack{filteredStacks.length !== 1 ? 's' : ''}
            </span>
          {:else}
            <span class="text-sm text-fg-muted">No active profile</span>
          {/if}
        </div>
        <Button
          variant="ghost"
          size="xs"
          class="shrink-0 text-fg-muted hover:bg-danger/10 hover:text-danger"
          title="Clear all stacks for this profile"
          disabled={stackCount < 1}
          onclick={() => {
            clearMode = 'all';
            clearDialogOpen = true;
          }}
        >
          <TrashCanOutline width="14" height="14" />
          <span class="text-nowrap">Clear Stacks</span>
        </Button>
        <Select
          value={filter}
          options={filterOptions}
          onchange={(v) => (filter = v as StackFilter)}
          size="xs"
          variant="ghost"
          class="w-40 shrink-0"
        />
      </div>

      <!-- Scrollable stack rows -->
      <div
        role="grid"
        aria-label="Stack list"
        class="grid flex-1 auto-rows-min grid-cols-[auto_auto_auto_1fr_auto_auto_auto] content-start overflow-y-auto"
      >
        {#if filteredStacks.length === 0}
          <div class="col-span-full flex min-h-32 items-center justify-center p-4">
            <p class="text-sm text-fg-faint">
              {#if session.activeStacks.length === 0}
                No stacks — add stacks from the grid
              {:else}
                No stacks match filter
              {/if}
            </p>
          </div>
        {:else}
          {#each filteredStacks as stack, i (`${stack.row},${stack.col}`)}
            {@const selected = session.isStackSelected(stack.row, stack.col)}
            {@render stackRow(stack, selected, i)}
          {/each}
        {/if}
      </div>
    </div>
  </Pane>

  <PaneDivider direction="vertical" />

  <!-- Sidebar (right) -->
  <Pane
    defaultSize={30}
    minSize={paneGroupSize.width > 0 ? (SIDEBAR_MIN_PX / paneGroupSize.width) * 100 : 25}
    maxSize={45}
  >
    <div class="flex h-full flex-col overflow-y-auto bg-canvas">
      {#if !hasSelection}
        <div class="flex flex-1 items-center justify-center p-3">
          <p class="text-sm text-fg-faint">Select stacks to edit</p>
        </div>
      {:else}
        <!-- Sidebar header -->
        <div class="space-y-2 px-4 py-2">
          {#if selectedStacks.length > 0}
            <div class="flex items-center justify-between">
              <span class="text-xs text-fg-muted">
                {selectedStacks.length} Stack{selectedStacks.length !== 1 ? 's' : ''}
              </span>
              <Button
                variant="ghost"
                size="xs"
                class="text-danger/80 hover:bg-danger/10 hover:text-danger"
                onclick={() => {
                  clearMode = 'selected';
                  clearDialogOpen = true;
                }}
              >
                Remove
              </Button>
            </div>
          {:else}
            <span class="text-xs text-fg-faint">No stacks at selected positions</span>
          {/if}
        </div>

        <!-- Stack properties -->
        {#if selectedStacks.length > 0}
          <div class="border-y border-border px-4 pb-5">
            <!-- Z Range -->
            <div class="space-y-3">
              <div class="flex items-center justify-between py-3">
                <span class="text-xs text-fg-muted">Z Range</span>
                {#if commonZStep !== undefined}
                  <span class="text-xs text-fg-muted tabular-nums">
                    {(commonZStep / 1000).toFixed(4)} mm per step
                  </span>
                {/if}
              </div>
              <div class="grid grid-cols-[3.5rem_1fr_auto] items-center gap-x-4 gap-y-4">
                <span class="text-xs text-fg-muted">Start</span>
                <SpinBox
                  value={(commonZStart ?? 0) / 1000}
                  placeholder={commonZStart === undefined ? 'mixed' : ''}
                  suffix="mm"
                  size="xs"
                  step={0.001}
                  decimals={3}
                  onChange={(v) => applyZRange('zStartUm', v * 1000)}
                />
                <div class="flex items-center gap-1">
                  <Button
                    variant="outline"
                    size="icon-xs"
                    title="Reset to profile default"
                    onclick={() => {
                      const gc = session.gridConfig;
                      if (gc) applyZRange('zStartUm', gc.default_z_start);
                    }}
                  >
                    <Restore width="14" height="14" />
                  </Button>
                  <Button
                    variant="outline"
                    size="xs"
                    title="Set from current Z position"
                    onclick={() => applyZRange('zStartUm', session.stage.z.position)}
                  >
                    Match FOV
                  </Button>
                </div>

                <span class="text-xs text-fg-muted">End</span>
                <SpinBox
                  value={(commonZEnd ?? 0) / 1000}
                  placeholder={commonZEnd === undefined ? 'mixed' : ''}
                  suffix="mm"
                  size="xs"
                  step={0.001}
                  decimals={3}
                  onChange={(v) => applyZRange('zEndUm', v * 1000)}
                />
                <div class="flex items-center gap-1">
                  <Button
                    variant="outline"
                    size="icon-xs"
                    title="Reset to profile default"
                    onclick={() => {
                      const gc = session.gridConfig;
                      if (gc) applyZRange('zEndUm', gc.default_z_end);
                    }}
                  >
                    <Restore width="14" height="14" />
                  </Button>
                  <Button
                    variant="outline"
                    size="xs"
                    title="Set from current Z position"
                    onclick={() => applyZRange('zEndUm', session.stage.z.position)}
                  >
                    Match FOV
                  </Button>
                </div>
              </div>
              <div class="flex items-center justify-between gap-4 text-xs text-fg-muted tabular-nums">
                <span class="w-3.5rem text-xs text-fg-muted">Range</span>
                <p>
                  <span>{(totalRange / 1000).toFixed(2)} mm</span>
                  <span class="mx-2">·</span>
                  <span>{totalFrames} frames</span>
                </p>
              </div>
            </div>
          </div>
        {/if}
      {/if}
    </div>
  </Pane>
</PaneGroup>

<!-- Clear stacks confirmation -->
<Dialog.Root bind:open={clearDialogOpen}>
  <Dialog.Portal>
    <Dialog.Overlay />
    <Dialog.Content>
      <Dialog.Header>
        <Dialog.Title>
          {clearMode === 'selected' ? 'Remove selected stacks' : 'Clear all stacks'}
        </Dialog.Title>
        <Dialog.Description>
          {#if clearMode === 'selected'}
            Remove {selectedStacks.length} selected stack{selectedStacks.length !== 1 ? 's' : ''} for
            <strong>{activeProfileLabel}</strong>?
          {:else}
            Remove all {stackCount} stack{stackCount !== 1 ? 's' : ''} for
            <strong>{activeProfileLabel}</strong>? The profile will be removed from the acquisition plan.
          {/if}
        </Dialog.Description>
      </Dialog.Header>
      <Dialog.Footer>
        <button
          onclick={() => (clearDialogOpen = false)}
          class="rounded border border-border px-3 py-1.5 text-sm text-fg-muted transition-colors hover:bg-element-hover hover:text-fg"
        >
          Cancel
        </button>
        <button
          onclick={() => {
            if (clearMode === 'selected') {
              removeSelectedStacks();
            } else {
              session.removeStacks(session.activeStacks.map((s) => ({ row: s.row, col: s.col })));
              clearDialogOpen = false;
            }
          }}
          class="rounded bg-danger px-3 py-1.5 text-sm text-danger-fg transition-colors hover:bg-danger/90"
        >
          {clearMode === 'selected' ? 'Remove' : 'Clear All'}
        </button>
      </Dialog.Footer>
    </Dialog.Content>
  </Dialog.Portal>
</Dialog.Root>
