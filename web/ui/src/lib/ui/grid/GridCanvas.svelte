<script lang="ts">
  import type { Session } from '$lib/main';
  import type { Component } from 'svelte';
  import type { GridConfig, LayerVisibility, StackOrder } from '$lib/main/types';
  import { STACK_ORDER_OPTIONS } from '$lib/main/types';
  import { Link, LinkOff, PanelLeft, GridLines, StackLight, ImageLight, GripVertical } from '$lib/icons';
  import { sanitizeString } from '$lib/utils';
  import XYPlane from './XYPlane.svelte';
  import ZPlane from './ZPlane.svelte';
  import { slide } from 'svelte/transition';
  import { watch } from 'runed';
  import { Button, Checkbox, Select, SortableList, SpinBox } from '../kit';

  interface Props {
    session: Session;
  }

  let { session }: Props = $props();

  let layers = $state<LayerVisibility>({ grid: true, stacks: true, path: true, fov: true, thumbnail: true });
  let sidebarOpen = $state(true);
  let offsetLinked = $state(false);
  let overlapLinked = $state(true);

  let gc = $derived<GridConfig | null>(session.rig_cfg.profiles[session.activeProfileId ?? '']?.grid ?? null);

  const layerItems: { key: keyof LayerVisibility; color: string; Icon: Component; title: string }[] = [
    { key: 'grid', color: 'text-fg-muted', Icon: GridLines, title: 'Toggle grid' },
    { key: 'stacks', color: 'text-info', Icon: StackLight, title: 'Toggle stacks' },
    { key: 'thumbnail', color: 'text-success', Icon: ImageLight, title: 'Toggle thumbnail' }
  ];

  watch(
    () => layers.grid,
    (grid, prev) => {
      if (grid && !prev) sidebarOpen = true;
    }
  );
</script>

{#if session.stage && session.stage.x && session.stage.y && session.stage.z}
  <div class="flex h-full">
    <!-- Grid controls sidebar (collapses when grid layer hidden) -->
    {#if gc && sidebarOpen}
      {@const gridLimX = (session.fov.width * (1 - (gc.overlap_x ?? 0.1))) / 1000}
      {@const gridLimY = (session.fov.height * (1 - (gc.overlap_y ?? 0.1))) / 1000}
      <div
        transition:slide={{ duration: 200, axis: 'x' }}
        class="flex shrink-0 flex-col gap-6 border-r border-border px-4 py-2"
        style="width: clamp(10rem, 25%, 16rem)"
      >
        <!-- Offset -->
        <div class="flex flex-col gap-2">
          <div class="flex items-center justify-between">
            <span class="text-xs font-medium text-fg-muted">Offset</span>
            <button
              class="flex h-4 w-4 items-center justify-center rounded text-fg-muted/50 transition-colors hover:text-fg"
              title={offsetLinked ? 'Unlink X/Y' : 'Link X/Y'}
              onclick={() => {
                offsetLinked = !offsetLinked;
                if (offsetLinked && gc) session.setGridOffset(gc.x_offset, gc.x_offset);
              }}
            >
              {#if offsetLinked}<Link class="h-3 w-3" />{:else}<LinkOff class="h-3 w-3" />{/if}
            </button>
          </div>
          {#if offsetLinked}
            <SpinBox
              value={gc.x_offset / 1000}
              min={-Math.min(gridLimX, gridLimY)}
              max={Math.min(gridLimX, gridLimY)}
              step={0.1}
              decimals={2}
              numCharacters={6}
              prefix="X / Y"
              suffix="mm"
              size="xs"
              variant="ghost"
              align="right"
              onChange={(v) => session.setGridOffset(v * 1000, v * 1000)}
            />
          {:else}
            <SpinBox
              value={gc.x_offset / 1000}
              min={-gridLimX}
              max={gridLimX}
              step={0.1}
              decimals={2}
              numCharacters={6}
              prefix="X"
              suffix="mm"
              size="xs"
              variant="ghost"
              align="right"
              onChange={(v) => session.setGridOffset(v * 1000, gc!.y_offset)}
            />
            <SpinBox
              value={gc.y_offset / 1000}
              min={-gridLimY}
              max={gridLimY}
              step={0.1}
              decimals={2}
              numCharacters={6}
              prefix="Y"
              suffix="mm"
              size="xs"
              variant="ghost"
              align="right"
              onChange={(v) => session.setGridOffset(gc!.x_offset, v * 1000)}
            />
          {/if}
        </div>

        <!-- Overlap -->
        <div class="flex flex-col gap-2">
          <div class="flex items-center justify-between">
            <span class="text-xs font-medium text-fg-muted">Overlap</span>
            <button
              class="flex h-4 w-4 items-center justify-center rounded text-fg-muted/50 transition-colors hover:text-fg"
              title={overlapLinked ? 'Unlink X/Y' : 'Link X/Y'}
              onclick={() => {
                overlapLinked = !overlapLinked;
                if (overlapLinked && gc) session.setGridOverlap(gc.overlap_x, gc.overlap_x);
              }}
            >
              {#if overlapLinked}<Link class="h-3 w-3" />{:else}<LinkOff class="h-3 w-3" />{/if}
            </button>
          </div>
          {#if overlapLinked}
            <SpinBox
              value={gc.overlap_x}
              min={0}
              max={0.5}
              step={0.01}
              decimals={3}
              numCharacters={6}
              prefix="X / Y"
              suffix="%"
              size="xs"
              variant="ghost"
              align="right"
              onChange={(v) => session.setGridOverlap(v, v)}
            />
          {:else}
            <SpinBox
              value={gc.overlap_x}
              min={0}
              max={0.5}
              step={0.01}
              decimals={3}
              numCharacters={6}
              prefix="X"
              suffix="%"
              size="xs"
              variant="ghost"
              align="right"
              onChange={(v) => session.setGridOverlap(v, gc!.overlap_y)}
            />
            <SpinBox
              value={gc.overlap_y}
              min={0}
              max={0.5}
              step={0.01}
              decimals={3}
              numCharacters={6}
              prefix="Y"
              suffix="%"
              size="xs"
              variant="ghost"
              align="right"
              onChange={(v) => session.setGridOverlap(gc!.overlap_x, v)}
            />
          {/if}
        </div>

        <!-- Z defaults -->
        <div class="flex flex-col gap-2">
          <span class="text-xs font-medium text-fg-muted">Default Z Range</span>
          <SpinBox
            value={session.acq.default_z_start / 1000}
            step={0.001}
            decimals={3}
            numCharacters={8}
            prefix="Start"
            suffix="mm"
            size="xs"
            variant="ghost"
            align="right"
            onChange={(v) => session.setGridZRange(v * 1000, session.acq.default_z_end)}
          />
          <SpinBox
            value={session.acq.default_z_end / 1000}
            step={0.001}
            decimals={3}
            numCharacters={8}
            prefix="End"
            suffix="mm"
            size="xs"
            variant="ghost"
            align="right"
            onChange={(v) => session.setGridZRange(session.acq.default_z_start, v * 1000)}
          />
        </div>

        <div class="flex-1"></div>

        <!-- Stack ordering -->
        <div class="flex flex-col gap-2">
          <span class="text-xs font-medium text-fg-muted">Stack Order</span>
          <Select
            size="xs"
            variant="ghost"
            value={session.stackOrderAlgorithm}
            options={STACK_ORDER_OPTIONS}
            onchange={(v) => session.setStackOrder(v as StackOrder)}
          />
          {#if session.acq.profile_order.length > 1}
            <div class="flex items-center gap-1.5 pl-1">
              <Checkbox checked={session.sortByProfile} onchange={(v) => session.setSortByProfile(v)} />
              <span class="text-xs text-fg-muted">By profile</span>
            </div>
            {#if session.sortByProfile}
              <SortableList.Root
                items={session.acq.profile_order.map((id) => ({ profile_id: id }))}
                key={(p) => p.profile_id}
                onReorder={(reordered) => session.reorderProfiles(reordered.map((p) => p.profile_id))}
                class="flex flex-col gap-1"
              >
                {#snippet item(profile)}
                  <SortableList.Item
                    item={profile}
                    class="flex items-center gap-1 rounded border border-transparent py-1 pr-2 pl-0.5 text-xs text-fg hover:border-fg/20"
                  >
                    <GripVertical width="12" height="12" class="shrink-0 text-fg-muted/50" />
                    {session.rig_cfg.profiles[profile.profile_id]?.label ?? sanitizeString(profile.profile_id)}
                  </SortableList.Item>
                {/snippet}
              </SortableList.Root>
            {/if}
          {/if}
        </div>
      </div>
    {/if}

    <!-- Right column: planes + footer -->
    <div class="flex min-w-0 flex-1 flex-col">
      <div class="flex min-h-0 min-w-0 flex-1 items-stretch gap-4 p-4">
        <XYPlane {session} bind:layers />
        <ZPlane {session} />
      </div>

      <!-- Stage position footer -->
      <div class="flex w-full flex-wrap items-center gap-7 border-t border-border py-2 pr-4 pl-2">
        <div class="flex items-center gap-1">
          <button
            class="flex cursor-pointer items-center justify-center rounded p-1 transition-colors {sidebarOpen
              ? 'text-fg'
              : 'text-fg-muted/50 hover:text-fg-muted'}"
            title={sidebarOpen ? 'Hide grid controls' : 'Show grid controls'}
            onclick={() => (sidebarOpen = !sidebarOpen)}
          >
            <PanelLeft width="14" height="14" />
          </button>
          <div class="mx-1 h-4 w-px bg-border"></div>
          {#each layerItems as { key, color, Icon, title } (key)}
            <button
              onclick={() => (layers[key] = !layers[key])}
              class="cursor-pointer rounded-full p-1 transition-colors {layers[key] ? `${color}` : 'text-fg-faint'}"
              {title}
            >
              <Icon width="14" height="14" />
            </button>
          {/each}
        </div>
        <div class="flex flex-1 items-center justify-end gap-4">
          {#if session.stage.x}
            <SpinBox
              value={session.stage.x.position / 1000}
              min={session.stage.x.lowerLimit / 1000}
              max={session.stage.x.upperLimit / 1000}
              step={0.01}
              decimals={3}
              numCharacters={8}
              size="xs"
              align="right"
              prefix="X"
              suffix="mm"
              color={session.stage.x.isMoving ? 'var(--danger)' : undefined}
              onChange={(v) => session.stage.x.move(v * 1000)}
            />
          {/if}
          {#if session.stage.y}
            <SpinBox
              value={session.stage.y.position / 1000}
              min={session.stage.y.lowerLimit / 1000}
              max={session.stage.y.upperLimit / 1000}
              step={0.01}
              decimals={3}
              numCharacters={8}
              size="xs"
              align="right"
              prefix="Y"
              suffix="mm"
              color={session.stage.y.isMoving ? 'var(--danger)' : undefined}
              onChange={(v) => session.stage.y.move(v * 1000)}
            />
          {/if}
          {#if session.stage.z}
            <SpinBox
              value={session.stage.z.position / 1000}
              min={session.stage.z.lowerLimit / 1000}
              max={session.stage.z.upperLimit / 1000}
              step={0.001}
              decimals={3}
              numCharacters={8}
              size="xs"
              align="right"
              prefix="Z"
              suffix="mm"
              color={session.stage.z.isMoving ? 'var(--danger)' : undefined}
              onChange={(v) => session.stage.z.move(v * 1000)}
            />
          {/if}
          <Button
            variant={session.stage.isMoving ? 'danger' : 'outline'}
            size="xs"
            onclick={() => session.stage.halt()}
            disabled={!session.stage.isMoving}
            aria-label="Halt stage"
          >
            Halt Stage
          </Button>
        </div>
      </div>
    </div>
  </div>
{:else}
  <div class="grid h-full w-full place-content-center">
    <p class="text-base text-fg-muted">Stage not available</p>
  </div>
{/if}
