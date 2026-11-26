<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { getInstrumentSelection, getVoxelStation } from '$lib/context.svelte';
  import { LinearAxis } from '$lib/core/device.svelte';
  import { Prefs } from '$lib/core/prefs';
  import {
    type OutlineKind,
    type Point as TaskPoint,
    SpimInstrument,
    SpimSession,
    type SpimTask
  } from '$lib/core/spim.svelte';
  import type { SpecimenAxis } from '$lib/core/types';
  import { SPATIAL_UNITS } from '$lib/features/run/StageNumericField.svelte';
  import { ContextMenu } from '@voxel/kit';
  import { reportFailure } from '@voxel/kit/failures';
  import { Crosshair, Focus, Fullscreen, Plus, Square } from '@voxel/kit/icons';

  import AxesMark from './AxesMark.svelte';
  import AxisStrip from './AxisStrip.svelte';
  import type { MenuSelection, NavigationTarget } from './context';
  import { type Bounds, Geometry, type Point, type Viewport } from './geometry';
  import LastRun from './LastRun.svelte';
  import Position from './Position.svelte';
  import { StagePlan, type Tile } from './stage-plan.svelte';
  import StageInputs from './StageInputs.svelte';
  import StagePlane, { type MenuTargets, type PlaneActions } from './StagePlane.svelte';
  import Tasks from './Tasks.svelte';
  import VolumeTooltip from './VolumeTooltip.svelte';
  import Zones from './Zones.svelte';

  // A new task's depth on the scan axis when no other task gives one.
  const DEPTH_UM = 100;
  const SCALE_STEPS = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000];

  const station = getVoxelStation();
  const selection = getInstrumentSelection();
  const name = $derived(page.params.instrument ?? '');
  const selected = $derived(page.params.taskId);
  const spim = $derived(selection.instrument instanceof SpimInstrument ? selection.instrument : undefined);
  const session = $derived(selection.session instanceof SpimSession ? selection.session : undefined);
  const plan = $derived(session ? new StagePlan(session) : undefined);
  const tasks = $derived(spim?.state.get('plan') ?? []);
  const unit = $derived(SPATIAL_UNITS[Prefs.spatialUnit.get()]);
  const running = $derived(session?.acquisition !== undefined);

  const axes = $derived(plan?.axes ?? { h: 'x' as const, v: 'y' as const, w: 'z' as const, scan: 'z' as const });
  const devices = $derived.by(() => {
    const config = spim?.config;
    return Object.fromEntries(
      StagePlan.AXES.map((axis) => [axis, config ? session?.device(config.stage[axis].device, LinearAxis) : undefined])
    ) as Record<SpecimenAxis, LinearAxis | undefined>;
  });
  const position = $derived(
    Object.fromEntries(StagePlan.AXES.map((axis) => [axis, devices[axis]?.position])) as Partial<
      Record<SpecimenAxis, number>
    >
  );
  const moving = $derived(StagePlan.AXES.some((axis) => devices[axis]?.isMoving));
  const limits = $derived(
    Object.fromEntries(StagePlan.AXES.map((axis) => [axis, devices[axis]?.limits])) as Partial<
      Record<SpecimenAxis, [number, number]>
    >
  );
  const ranges = $derived(
    Object.fromEntries(
      StagePlan.AXES.map((axis) => {
        const specimen = spim?.config?.stage[axis].specimen;
        const range = specimen ? ([Math.min(...specimen), Math.max(...specimen)] as [number, number]) : limits[axis];
        return [axis, range];
      })
    ) as Partial<Record<SpecimenAxis, [number, number]>>
  );
  const travel = $derived(boundsOf(limits));
  const specimen = $derived(boundsOf(ranges));
  const stageAt = $derived(
    position[axes.h] !== undefined && position[axes.v] !== undefined
      ? { x: position[axes.h]!, y: position[axes.v]! }
      : null
  );
  // 1 capture of the active profile: its span on each tiled axis; it is a line along the scan axis.
  const frame = $derived.by(() => {
    const tile = session?.newTaskTile;
    const size = (axis: SpecimenAxis) => (tile?.[axis] ? tile[axis]![1] - tile[axis]![0] : 0);
    return tile ? { width: size(axes.h), height: size(axes.v) } : null;
  });
  const home = $derived.by(() => {
    if (!specimen) return null;
    const parts: Bounds[] = [specimen];
    const tasksBox = plan?.taskBounds();
    if (tasksBox) parts.push(tasksBox);
    if (stageAt) parts.push(Geometry.box(stageAt, stageAt));
    return Geometry.union(parts);
  });

  let viewport = $state<Viewport | null>(null);
  let marquee = $state<Bounds | null>(null);
  let hovered = $state<Tile | null>(null);
  let tip = $state(false);
  let chooser = $state.raw<{ screen: Point; tasks: string[] } | null>(null);
  let target = $state<Partial<Record<SpecimenAxis, number>>>({});
  let planeLayer = $state<StagePlane>();

  $effect(() => {
    if (!moving) target = {};
  });
  $effect(() => {
    tip = false;
    if (!hovered) return;
    const timer = setTimeout(() => (tip = true), 1000);
    return () => clearTimeout(timer);
  });

  function boundsOf(spans: Partial<Record<SpecimenAxis, [number, number]>>): Bounds | null {
    const a = spans[axes.h];
    const b = spans[axes.v];
    return a && b ? { minX: a[0], maxX: a[1], minY: b[0], maxY: b[1] } : null;
  }

  function taskHref(id: string): string {
    return selection.href(name, `run/${encodeURIComponent(id)}`);
  }

  function tasksAt(names: string[]): string[] {
    return [...new Set(names.filter((n) => n.startsWith('task:')).map((n) => n.slice('task:'.length)))];
  }

  function move(point: Partial<Record<SpecimenAxis, number>>): void {
    if (!session) return;
    target = { ...target, ...point };
    reportFailure(session.moveStage(point));
  }

  async function add(kind: OutlineKind, points: TaskPoint[]): Promise<void> {
    if (!session) return;
    const last = tasks.at(-1)?.region.bounds;
    const depth = last ? Math.abs(last[1] - last[0]) : DEPTH_UM;
    const start = position[axes.scan] ?? 0;
    const task = session.draftTask(kind, points, [start, start + depth]);
    if (!task) return;
    await session.addTask(task);
    await goto(taskHref(task.id));
  }

  /** A point on the map with the stage's value on the third axis, as a position on the 2 tiled axes. */
  function tiledPoint(point: Point): TaskPoint {
    const at = { ...position, [axes.h]: point.x, [axes.v]: point.y };
    const tiled = StagePlan.AXES.filter((axis) => axis !== axes.scan);
    return Object.fromEntries(tiled.map((axis) => [axis, at[axis] ?? 0]));
  }

  function boxPoints(box: Bounds): TaskPoint[] {
    return [
      { [axes.h]: box.minX, [axes.v]: box.minY },
      { [axes.h]: box.maxX, [axes.v]: box.maxY }
    ];
  }

  function updateOutline(task: SpimTask, points: TaskPoint[]): void {
    reportFailure(
      session?.updateTask(task.id, {
        region: { ...task.region, outline: { ...task.region.outline, points } }
      })
    );
  }

  function scaleBar(scale: number, width: number) {
    const um = SCALE_STEPS.findLast((step) => step * scale <= width * 0.2) ?? SCALE_STEPS[0];
    return { px: um * scale, label: um >= 1000 ? `${um / 1000} mm` : `${um} µm` };
  }

  function shown(value: number): string {
    return (value / unit.scale).toFixed(unit.decimals);
  }
</script>

{#snippet go(target: NavigationTarget, actions: PlaneActions)}
  <ContextMenu.Item
    disabled={running}
    onpointerenter={() => actions.preview(target.point)}
    onpointerleave={() => actions.preview(null)}
    onSelect={() => move({ [axes.h]: target.point.x, [axes.v]: target.point.y })}
  >
    {target.label}
  </ContextMenu.Item>
{/snippet}

{#snippet addAt(target: NavigationTarget)}
  {@const size = plan?.outlinesShown ? target.size : undefined}
  <ContextMenu.Item
    disabled={running}
    onSelect={() =>
      reportFailure(
        size
          ? add(
              'bounding_box',
              boxPoints({
                minX: target.point.x - size.width / 2,
                maxX: target.point.x + size.width / 2,
                minY: target.point.y - size.height / 2,
                maxY: target.point.y + size.height / 2
              })
            )
          : add('explicit_points', [tiledPoint(target.point)])
      )}
  >
    {target.label}
  </ContextMenu.Item>
{/snippet}

{#snippet menu(selection: MenuSelection, targets: MenuTargets, actions: PlaneActions)}
  {@const region = selection.region}
  {@const clicked = { id: 'clicked', label: 'Clicked position', point: selection.point }}
  <div class="px-2 py-1.5 font-mono text-sm text-fg-muted tabular-nums">
    {axes.h.toUpperCase()}
    {shown(selection.point.x)}, {axes.v.toUpperCase()}
    {shown(selection.point.y)}
    {unit.label}
  </div>
  <ContextMenu.Sub>
    <ContextMenu.SubTrigger><Plus class="size-3.5" />Add task</ContextMenu.SubTrigger>
    <ContextMenu.SubContent class="min-w-48">
      {#if stageAt}
        {@render addAt({ id: 'stage', label: 'Current position', point: stageAt })}
      {/if}
      {@render addAt(clicked)}
      {#each targets.addTask as target (target.id)}
        {@render addAt(target)}
      {/each}
      {#if region && plan?.outlinesShown}
        <ContextMenu.Item
          disabled={running}
          onSelect={() => reportFailure(add('bounding_box', boxPoints(region)).then(() => (marquee = null)))}
        >
          Selected region
        </ContextMenu.Item>
      {/if}
    </ContextMenu.SubContent>
  </ContextMenu.Sub>
  {#if moving}
    <ContextMenu.Item
      variant="destructive"
      onSelect={() => StagePlan.AXES.forEach((axis) => reportFailure(devices[axis]?.halt()))}
    >
      <Square class="size-3.5" />Halt
    </ContextMenu.Item>
  {:else}
    <ContextMenu.Sub>
      <ContextMenu.SubTrigger disabled={running}><Crosshair class="size-3.5" />Go to</ContextMenu.SubTrigger>
      <ContextMenu.SubContent class="max-h-72 min-w-56 overflow-y-auto">
        {@render go(clicked, actions)}
        {#each targets.goTo as target (target.id)}
          {@render go(target, actions)}
        {/each}
      </ContextMenu.SubContent>
    </ContextMenu.Sub>
  {/if}
  <ContextMenu.Sub>
    <ContextMenu.SubTrigger><Fullscreen class="size-3.5" />Fit</ContextMenu.SubTrigger>
    <ContextMenu.SubContent class="min-w-48">
      {#if travel}
        {@const all = {
          minX: travel.minX - (frame?.width ?? 0) / 2,
          maxX: travel.maxX + (frame?.width ?? 0) / 2,
          minY: travel.minY - (frame?.height ?? 0) / 2,
          maxY: travel.maxY + (frame?.height ?? 0) / 2
        }}
        <ContextMenu.Item onSelect={() => actions.fit(all)}>Stage travel</ContextMenu.Item>
      {/if}
      {#if specimen}
        {@const range = specimen}
        <ContextMenu.Item onSelect={() => actions.fit(range)}>Specimen range</ContextMenu.Item>
      {/if}
      {#each targets.fit.filter((target) => !target.group) as target (target.id)}
        <ContextMenu.Item onSelect={() => actions.fit(target.bounds)}>{target.label}</ContextMenu.Item>
      {/each}
      {#if region}
        <ContextMenu.Item onSelect={() => actions.fit(region)}>Selected region</ContextMenu.Item>
      {/if}
      {#each [...new Set(targets.fit.flatMap((target) => target.group ?? []))] as group (group)}
        <ContextMenu.Separator />
        <ContextMenu.Group>
          <ContextMenu.GroupHeading class="text-fg-muted">{group}</ContextMenu.GroupHeading>
          {#each targets.fit.filter((target) => target.group === group) as target (target.id)}
            <ContextMenu.Item onSelect={() => actions.fit(target.bounds)}>
              <span class={target.id.startsWith('task:') ? 'font-mono' : ''}>{target.label}</span>
            </ContextMenu.Item>
          {/each}
        </ContextMenu.Group>
      {/each}
    </ContextMenu.SubContent>
  </ContextMenu.Sub>
  <ContextMenu.Item disabled={!stageAt} onSelect={() => stageAt && actions.center(stageAt)}>
    <Focus class="size-3.5" />Pan to current position
  </ContextMenu.Item>
{/snippet}

<div class="flex h-full min-h-0 flex-col bg-pane">
  {#if plan && travel && specimen && home && limits[axes.w] && ranges[axes.w]}
    <div class="flex min-h-0 flex-1 overflow-hidden">
      <AxisStrip
        axis={axes.w}
        travel={limits[axes.w]!}
        specimen={ranges[axes.w]!}
        spans={selected ? plan.spans(selected) : []}
        stage={position[axes.w]}
        target={target[axes.w] ?? null}
        {unit}
        disabled={running}
        onmove={(value) => move({ [axes.w]: value })}
      />
      <div class="relative min-h-0 min-w-0 flex-1">
        <StagePlane
          bind:this={planeLayer}
          {travel}
          reach={frame ? { width: frame.width / 2, height: frame.height / 2 } : undefined}
          {specimen}
          {home}
          bind:viewport
          bind:marquee
          {menu}
          onclick={(_, names, screen) => {
            const found = tasksAt(names);
            if (found.length === 1) void goto(taskHref(found[0]));
            chooser = found.length > 1 ? { screen, tasks: found } : null;
          }}
          onescape={() => {
            chooser = null;
            if (selected !== undefined) void goto(selection.href(name, 'run'));
          }}
        >
          {#snippet overlay(view, width, height, cursor)}
            {@const bar = scaleBar(view.scale, width)}
            {#if chooser}
              <div
                class="absolute z-20 w-40 overflow-hidden frame-floating py-1"
                style:left="{Math.min(chooser.screen.x + 8, width - 168)}px"
                style:top="{Math.min(chooser.screen.y + 8, height - 40 - chooser.tasks.length * 30)}px"
                role="menu"
                aria-label="Open task"
              >
                <div class="px-2 py-1 text-sm text-fg-muted">Open task</div>
                {#each chooser.tasks as id (id)}
                  <button
                    type="button"
                    role="menuitem"
                    class="flex h-7 w-full items-center px-2 text-left font-mono hover:bg-element-hover"
                    onclick={() => {
                      chooser = null;
                      void goto(taskHref(id));
                    }}
                  >
                    {id}
                  </button>
                {/each}
              </div>
            {/if}
            {#if tip && hovered}
              {@const at = cursor ? Geometry.project(cursor, view) : { x: 0, y: 0 }}
              <VolumeTooltip
                tile={hovered}
                {plan}
                visit={session?.acquisition?.visit ?? null}
                x={at.x}
                y={at.y}
                {width}
                {height}
              />
            {/if}
            <AxesMark right={axes.h} up={axes.v} class="pointer-events-none absolute top-4 right-4" />
            <div
              class="pointer-events-none absolute right-4 bottom-4 flex flex-col items-end gap-2 font-mono text-xs text-fg-muted tabular-nums"
            >
              {#if cursor}
                <span class="flex gap-2.5">
                  <span><span class="mr-1 opacity-70">{axes.h.toUpperCase()}</span>{shown(cursor.x)}</span>
                  <span><span class="mr-1 opacity-70">{axes.v.toUpperCase()}</span>{shown(cursor.y)}</span>
                  {#if !Geometry.contains(travel, cursor)}<span class="text-warning-fg">Out of range</span>{/if}
                </span>
              {/if}
              <span>{bar.label}</span>
              <span class="block h-0.75 rounded-xs bg-fg-muted" style:width="{bar.px}px"></span>
            </div>
            <StageInputs
              third={axes.w}
              plane={[axes.h, axes.v]}
              {position}
              {unit}
              right={Math.max(bar.px, 48) + 32}
              disabled={running || !session}
              onmove={(axis, value) => move({ [axis]: value })}
            />
          {/snippet}
          <Zones {plan} {unit} editable={!running} onrule={(device, rule) => session?.setPositionRule(device, rule)} />
          <LastRun run={station.lastRun} h={axes.h} v={axes.v} hidden={running} />
          <Tasks
            {plan}
            {tasks}
            {selected}
            progress={session?.acquisition ? { visit: session.acquisition.visit } : null}
            editable={!running}
            bind:hovered
            onoutline={updateOutline}
          />
          <Position
            position={stageAt}
            {frame}
            target={target[axes.h] !== undefined || target[axes.v] !== undefined
              ? { x: target[axes.h] ?? stageAt?.x ?? 0, y: target[axes.v] ?? stageAt?.y ?? 0 }
              : null}
            oncenter={() => stageAt && planeLayer?.center(stageAt)}
          />
        </StagePlane>
      </div>
    </div>
  {:else}
    <div class="grid flex-1 place-items-center text-sm text-fg-muted">
      {session ? 'Waiting for the stage limits' : 'Open the instrument to see the stage'}
    </div>
  {/if}
</div>
