<script lang="ts">
  import { getSessionContext } from '$lib/context';
  import { Button, Dialog, DropdownMenu, NudgeInput, Select, SpinBox } from '$lib/ui/kit';
  import { Pane, PaneGroup } from 'paneforge';
  import PaneDivider from '$lib/ui/kit/PaneDivider.svelte';
  import { sanitizeString, cn, createPaneMinSize } from '$lib/utils';
  import { ChevronDown, ChevronRight, EllipsisVertical } from '$lib/icons';
  import StackStatusIcon from '$lib/ui/StackStatusIcon.svelte';
  import { watch } from 'runed';
  import { SvelteMap, SvelteSet } from 'svelte/reactivity';
  import type { Stack, StackStatus } from '$lib/main/types';
  import StackOrdering from '$lib/ui/StackOrdering.svelte';

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

  // --- Profile groups ---

  interface ProfileGroup {
    profileId: string;
    label: string;
    stacks: Stack[];
    isActive: boolean;
  }

  let collapsedProfiles = new SvelteSet<string>();

  const profileGroups = $derived.by<ProfileGroup[]>(() => {
    const allStacks = filter === 'all' ? session.stacks : session.stacks.filter((s) => s.status === filter);

    const groupMap = new SvelteMap<string, Stack[]>();
    for (const s of allStacks) {
      const group = groupMap.get(s.profile_id);
      if (group) group.push(s);
      else groupMap.set(s.profile_id, [s]);
    }

    const activeId = session.activeProfileId;
    const profileOrder = session.acq.profile_order;

    const groups: ProfileGroup[] = [];
    for (const [profileId, stacks] of groupMap) {
      groups.push({
        profileId,
        label: session.config.profiles[profileId]?.label ?? sanitizeString(profileId),
        stacks,
        isActive: profileId === activeId
      });
    }

    groups.sort((a, b) => {
      if (a.isActive !== b.isActive) return a.isActive ? -1 : 1;
      return profileOrder.indexOf(a.profileId) - profileOrder.indexOf(b.profileId);
    });

    return groups;
  });

  // Flat list of visible stacks (for shift-click range selection)
  const flatStacks = $derived(profileGroups.flatMap((g) => (collapsedProfiles.has(g.profileId) ? [] : g.stacks)));

  const totalCount = $derived(
    filter === 'all' ? session.stacks.length : session.stacks.filter((s) => s.status === filter).length
  );

  const hasSelection = $derived(session.selectedStacks.length > 0);

  // Acquisition order: index of each stack in the plan's ordered stacks list
  const acquisitionOrder = $derived(new Map(session.stacks.map((s, i) => [s.stack_id, i + 1])));

  // --- Merged Z values for batch editing ---

  function commonValue(values: number[]): number | undefined {
    if (values.length === 0) return undefined;
    const first = values[0];
    return values.every((v) => v === first) ? first : undefined;
  }

  const selectedStacks = $derived(session.selectedStacks);

  // Common values in mm (undefined = mixed)
  function toMm(v: number | undefined): number {
    return v !== undefined ? v / 1000 : NaN;
  }
  const commonX = $derived(toMm(commonValue(selectedStacks.map((s) => s.x))));
  const commonY = $derived(toMm(commonValue(selectedStacks.map((s) => s.y))));
  const commonZStart = $derived(toMm(commonValue(selectedStacks.map((s) => s.z_start))));
  const commonZEnd = $derived(toMm(commonValue(selectedStacks.map((s) => s.z_end))));
  const commonFrames = $derived(commonValue(selectedStacks.map((s) => s.num_frames)) ?? NaN);
  const commonRange = $derived(
    !Number.isNaN(commonZStart) && !Number.isNaN(commonZEnd) ? Math.abs(commonZEnd - commonZStart) : NaN
  );

  // FOV — show "Mixed" when stacks have different FOVs
  const commonFovW = $derived(commonValue(selectedStacks.map((s) => s.w)));
  const commonFovH = $derived(commonValue(selectedStacks.map((s) => s.h)));

  // Profile breakdown for header badges
  const profileBreakdown = $derived.by(() => {
    const counts = new SvelteMap<string, number>();
    for (const s of selectedStacks) {
      counts.set(s.profile_id, (counts.get(s.profile_id) ?? 0) + 1);
    }
    return [...counts.entries()].map(([id, count]) => ({
      id,
      label: session.config.profiles[id]?.label ?? sanitizeString(id),
      count
    }));
  });

  // Status breakdown for header
  const statusBreakdown = $derived.by(() => {
    const counts = new SvelteMap<string, number>();
    for (const s of selectedStacks) {
      counts.set(s.status, (counts.get(s.status) ?? 0) + 1);
    }
    return [...counts.entries()] as [StackStatus, number][];
  });

  // --- Actions ---

  function applyPosition(axis: 'x' | 'y', value: number) {
    if (selectedStacks.length === 0) return;
    session.editStacks(
      selectedStacks.map((s) => ({
        stackId: s.stack_id,
        ...(axis === 'x' ? { x: value } : { y: value })
      }))
    );
  }

  function applyNudge(dx: number, dy: number) {
    if (selectedStacks.length === 0 || (dx === 0 && dy === 0)) return;
    session.editStacks(
      selectedStacks.map((s) => ({
        stackId: s.stack_id,
        x: s.x + dx,
        y: s.y + dy
      })),
      'nudge'
    );
  }

  function applyFrameCount(frames: number) {
    if (selectedStacks.length === 0 || frames < 1) return;
    session.editStacks(
      selectedStacks.map((s) => ({
        stackId: s.stack_id,
        zEndUm: s.z_start + (frames - 1) * s.z_step
      }))
    );
  }

  function applyZRange(field: 'zStartUm' | 'zEndUm', value: number) {
    if (selectedStacks.length === 0) return;
    session.editStacks(
      selectedStacks.map((s) => ({
        stackId: s.stack_id,
        zStartUm: field === 'zStartUm' ? value : s.z_start,
        zEndUm: field === 'zEndUm' ? value : s.z_end
      }))
    );
  }

  function removeSelectedStacks() {
    const stacks = session.selectedStacks;
    if (stacks.length === 0) return;
    session.removeStacks(stacks.map((s) => s.stack_id));
    clearDialogOpen = false;
  }

  // --- Selection ---

  function handleRowClick(stack: Stack, e: MouseEvent) {
    if (e.metaKey || e.ctrlKey) {
      if (session.isStackSelected(stack.stack_id)) {
        session.removeStacksFromSelection([stack]);
      } else {
        session.addStacksToSelection([stack]);
      }
    } else if (e.shiftKey && lastClickedId) {
      const lastIdx = flatStacks.findIndex((s) => s.stack_id === lastClickedId);
      const curIdx = flatStacks.findIndex((s) => s.stack_id === stack.stack_id);
      if (lastIdx >= 0 && curIdx >= 0) {
        const from = Math.min(lastIdx, curIdx);
        const to = Math.max(lastIdx, curIdx);
        session.selectStacks(flatStacks.slice(from, to + 1));
      } else {
        session.selectStacks([stack]);
      }
    } else if (session.isStackSelected(stack.stack_id) && session.selectedStacks.length === 1) {
      session.clearStackSelection();
    } else {
      session.selectStacks([stack]);
    }
    lastClickedId = stack.stack_id;
  }

  let lastClickedId = $state<string | null>(null);

  function toggleGroup(profileId: string) {
    if (collapsedProfiles.has(profileId)) {
      collapsedProfiles.delete(profileId);
    } else {
      collapsedProfiles.add(profileId);
    }
  }

  // --- Auto-scroll to selection from canvas ---

  watch(
    () => session.selectedStacks[0],
    (first) => {
      if (!first) return;
      const el = document.getElementById(`stack-${first.stack_id}`);
      el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  );

  // --- Clear dialog ---

  let clearDialogOpen = $state(false);
  let clearMode = $state<'selected' | 'profile'>('selected');
  let clearProfileId = $state<string>('');
  let clearProfileLabel = $derived(session.config.profiles[clearProfileId]?.label ?? sanitizeString(clearProfileId));

  // --- Pane sizing (pixel-based min for sidebar) ---

  let paneGroupEl = $state<HTMLElement | null>(null);
  const sidebarMin = createPaneMinSize(() => paneGroupEl, 350);
</script>

{#snippet stackRow(stack: Stack, selected: boolean)}
  <div
    id="stack-{stack.stack_id}"
    role="row"
    tabindex="0"
    aria-selected={selected}
    aria-label="Stack at ({(stack.x / 1000).toFixed(2)}, {(stack.y / 1000).toFixed(2)}) mm, {stack.status}"
    data-stack-status={stack.status}
    class={cn(
      'col-span-full grid cursor-default grid-cols-subgrid items-center gap-x-3 px-3 py-1.5 text-left text-xs transition-colors select-none',
      'border-b border-border/50',
      selected ? 'bg-element-selected/50' : 'hover:bg-element-hover/30'
    )}
    onclick={(e) => handleRowClick(stack, e)}
    onkeydown={(e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        handleRowClick(stack, e as unknown as MouseEvent);
      }
    }}
  >
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
      {@const order = acquisitionOrder.get(stack.stack_id)}
      <span class="min-w-[5ch] justify-self-end text-right text-fg-faint tabular-nums">#{order ?? '?'}</span>
    {/if}

    <!-- Status -->
    <StackStatusIcon status={stack.status} class="justify-self-end" />
  </div>
{/snippet}

<PaneGroup bind:ref={paneGroupEl} direction="horizontal" autoSaveId="setup.plan" class="h-full">
  <!-- Stack list (main area) -->
  <Pane minSize={40}>
    <div class="flex h-full flex-col overflow-hidden pb-2">
      <!-- List header -->
      <div class="flex items-center gap-2 border-b border-border px-3 py-2">
        <span class="text-xs text-fg-muted">
          {totalCount} stack{totalCount !== 1 ? 's' : ''}
        </span>
        <div class="flex-1"></div>
        <Select
          value={filter}
          options={filterOptions}
          onchange={(v) => (filter = v as StackFilter)}
          size="xs"
          variant="ghost"
          class="w-36 shrink-0"
        />
      </div>

      <!-- Scrollable grouped stack rows -->
      <div
        role="grid"
        aria-label="Stack list"
        class="grid flex-1 auto-rows-min grid-cols-[auto_auto_auto_1fr_auto_auto] content-start overflow-y-auto"
      >
        {#if profileGroups.length === 0}
          <div class="col-span-full flex min-h-32 items-center justify-center p-4">
            <p class="text-sm text-fg-faint">
              {#if session.stacks.length === 0}
                No stacks — add stacks from the grid
              {:else}
                No stacks match filter
              {/if}
            </p>
          </div>
        {:else}
          {#each profileGroups as group (group.profileId)}
            {@const collapsed = collapsedProfiles.has(group.profileId)}
            <!-- Profile group header -->
            <div class="col-span-full flex items-center gap-2 px-3 py-1.5">
              <button
                class="flex cursor-pointer items-center gap-1.5 bg-transparent p-0 text-xs text-fg-muted transition-colors hover:text-fg"
                onclick={() => toggleGroup(group.profileId)}
              >
                {#if collapsed}
                  <ChevronRight width="12" height="12" />
                {:else}
                  <ChevronDown width="12" height="12" />
                {/if}
                <span class={cn('font-semibold', group.isActive ? 'text-info' : 'text-fg')}>{group.label}</span>
                <span class="text-fg-faint">({group.stacks.length})</span>
              </button>
              <div class="flex-1"></div>
              <button
                class="cursor-pointer bg-transparent p-0 text-xs text-fg-muted transition-colors hover:text-danger"
                onclick={() => {
                  clearMode = 'profile';
                  clearProfileId = group.profileId;
                  clearDialogOpen = true;
                }}
              >
                Clear
              </button>
            </div>
            <!-- Stack rows -->
            {#if !collapsed}
              {#each group.stacks as stack (stack.stack_id)}
                {@const selected = session.isStackSelected(stack.stack_id)}
                {@render stackRow(stack, selected)}
              {/each}
            {/if}
          {/each}
        {/if}
      </div>
    </div>
  </Pane>

  <PaneDivider direction="vertical" />

  <!-- Sidebar (right) -->
  <Pane defaultSize={30} minSize={sidebarMin.value} maxSize={45}>
    <div class="flex h-full flex-col overflow-y-auto bg-canvas">
      {#if !hasSelection}
        <div class="flex flex-1 items-center justify-center p-3">
          <p class="text-sm text-fg-faint">Select stacks to edit</p>
        </div>
      {:else}
        <!-- Sidebar header + properties -->
        {#if selectedStacks.length > 0}
          {@const actionBtnCn =
            'inline-flex w-3 items-center justify-center cursor-pointer text-fg-faint hover:text-fg transition-colors'}
          <div class="flex items-center justify-between px-4 py-2">
            <span class="text-xs text-fg-muted">
              {selectedStacks.length} Stack{selectedStacks.length !== 1 ? 's' : ''}
            </span>
            <Button
              variant="ghost"
              size="xs"
              class="-mx-2 text-danger/80 hover:bg-danger/10 hover:text-danger"
              onclick={() => {
                clearMode = 'selected';
                clearDialogOpen = true;
              }}
            >
              Remove
            </Button>
          </div>

          <hr class="border-border" />
          <div class="px-4 py-2">
            <div class="-mr-1 grid grid-cols-[minmax(7rem,auto)_1fr_auto] items-center gap-x-1 gap-y-1.5">
              <!-- Profile -->
              <span class="flex h-ui-xs items-center text-[10px] text-fg-faint"
                >Profile{profileBreakdown.length > 1 ? 's' : ''}</span
              >
              <span class="col-span-2 text-[10px] text-fg-muted">
                {#each profileBreakdown as p, i (i)}
                  {#if i > 0},{/if}
                  {p.label}{profileBreakdown.length > 1 ? ` (${p.count})` : ''}
                {/each}
              </span>

              <!-- Status -->
              <span class="flex h-ui-xs items-center text-[10px] text-fg-faint">Status</span>
              <span class="col-span-2 text-[10px] text-fg-muted">
                {#each statusBreakdown as [status, count], i (i)}
                  {#if i > 0}
                    ·
                  {/if}
                  {count}
                  {status}
                {/each}
              </span>

              <hr class="col-span-full -mx-4 mb-2 border-border" />

              <!-- X Position -->
              <span class="text-xs text-fg-muted">X Position</span>
              <SpinBox
                value={commonX}
                suffix="mm"
                size="xs"
                step={0.1}
                decimals={4}
                onChange={(v) => applyPosition('x', v * 1000)}
              />
              <DropdownMenu.Root>
                <DropdownMenu.Trigger class={actionBtnCn}>
                  <EllipsisVertical width="14" height="14" />
                </DropdownMenu.Trigger>
                <DropdownMenu.Content align="end">
                  <DropdownMenu.Item
                    onclick={() => applyPosition('x', session.stage.x.position - session.stage.x.lowerLimit)}
                  >
                    Match stage X
                  </DropdownMenu.Item>
                </DropdownMenu.Content>
              </DropdownMenu.Root>

              <!-- Y Position -->
              <span class="text-xs text-fg-muted">Y Position</span>
              <SpinBox
                value={commonY}
                suffix="mm"
                size="xs"
                step={0.1}
                decimals={4}
                onChange={(v) => applyPosition('y', v * 1000)}
              />
              <DropdownMenu.Root>
                <DropdownMenu.Trigger class={actionBtnCn}>
                  <EllipsisVertical width="14" height="14" />
                </DropdownMenu.Trigger>
                <DropdownMenu.Content align="end">
                  <DropdownMenu.Item
                    onclick={() => applyPosition('y', session.stage.y.position - session.stage.y.lowerLimit)}
                  >
                    Match stage Y
                  </DropdownMenu.Item>
                </DropdownMenu.Content>
              </DropdownMenu.Root>

              <!-- Nudge X -->
              <span class="text-xs text-fg-muted">Nudge X</span>
              <NudgeInput
                prefix="dX"
                suffix="mm"
                size="xs"
                step={0.1}
                fineStep={0.01}
                decimals={4}
                onNudge={(v) => applyNudge(v * 1000, 0)}
              />
              <span></span>

              <!-- Nudge Y -->
              <span class="text-xs text-fg-muted">Nudge Y</span>
              <NudgeInput
                prefix="dY"
                suffix="mm"
                size="xs"
                step={0.1}
                fineStep={0.01}
                decimals={4}
                onNudge={(v) => applyNudge(0, v * 1000)}
              />
              <span></span>

              <!-- Z Start -->
              <span class="text-xs text-fg-muted">Z Start</span>
              <SpinBox
                value={commonZStart}
                suffix="mm"
                size="xs"
                step={0.001}
                decimals={3}
                onChange={(v) => applyZRange('zStartUm', v * 1000)}
              />
              <DropdownMenu.Root>
                <DropdownMenu.Trigger class={actionBtnCn}>
                  <EllipsisVertical width="14" height="14" />
                </DropdownMenu.Trigger>
                <DropdownMenu.Content align="end">
                  <DropdownMenu.Item onclick={() => applyZRange('zStartUm', session.stage.z.position)}>
                    Match stage Z
                  </DropdownMenu.Item>
                  <DropdownMenu.Item onclick={() => applyZRange('zStartUm', session.acq.default_z_start)}>
                    Reset to default
                  </DropdownMenu.Item>
                </DropdownMenu.Content>
              </DropdownMenu.Root>

              <!-- Z End -->
              <span class="text-xs text-fg-muted">Z End</span>
              <SpinBox
                value={commonZEnd}
                suffix="mm"
                size="xs"
                step={0.001}
                decimals={3}
                onChange={(v) => applyZRange('zEndUm', v * 1000)}
              />
              <DropdownMenu.Root>
                <DropdownMenu.Trigger class={actionBtnCn}>
                  <EllipsisVertical width="14" height="14" />
                </DropdownMenu.Trigger>
                <DropdownMenu.Content align="end">
                  <DropdownMenu.Item onclick={() => applyZRange('zEndUm', session.stage.z.position)}>
                    Match stage Z
                  </DropdownMenu.Item>
                  <DropdownMenu.Item onclick={() => applyZRange('zEndUm', session.acq.default_z_end)}>
                    Reset to default
                  </DropdownMenu.Item>
                </DropdownMenu.Content>
              </DropdownMenu.Root>

              <!-- Z Range -->
              <span class="text-xs text-fg-muted">Z Range</span>
              <SpinBox
                value={commonFrames}
                min={1}
                step={1}
                decimals={0}
                suffix={!Number.isNaN(commonRange) ? `frames · ${commonRange.toFixed(3)} mm` : 'frames'}
                size="xs"
                onChange={(v) => applyFrameCount(v)}
              />
              <span></span>

              <!-- FOV -->
              <span class="text-xs text-fg-muted">FOV</span>
              <div class="flex items-center gap-1">
                <SpinBox
                  value={commonFovW ?? NaN}
                  variant="ghost"
                  appearance="bordered"
                  size="xs"
                  disabled
                  decimals={0}
                  suffix="µm"
                  class="flex-1"
                />
                <span class="text-xs text-fg-faint">×</span>
                <SpinBox
                  value={commonFovH ?? NaN}
                  variant="ghost"
                  appearance="bordered"
                  size="xs"
                  disabled
                  decimals={0}
                  suffix="µm"
                  class="flex-1"
                />
              </div>
            </div>
          </div>
          <hr class="my-2 border-border" />
        {/if}
      {/if}

      <!-- Stack ordering (always visible) -->
      {#if session.stacks.length > 0}
        <div class="@container mt-auto border-t border-border px-4 py-3">
          <StackOrdering {session} />
        </div>
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
          {clearMode === 'selected' ? 'Remove selected stacks' : `Clear stacks for ${clearProfileLabel}`}
        </Dialog.Title>
        <Dialog.Description>
          {#if clearMode === 'selected'}
            Remove {selectedStacks.length} selected stack{selectedStacks.length !== 1 ? 's' : ''}?
          {:else}
            {@const count = session.stacks.filter((s) => s.profile_id === clearProfileId).length}
            Remove all {count} stack{count !== 1 ? 's' : ''} for
            <strong>{clearProfileLabel}</strong>?
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
              session.removeStacks(
                session.stacks.filter((s) => s.profile_id === clearProfileId).map((s) => s.stack_id)
              );
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
