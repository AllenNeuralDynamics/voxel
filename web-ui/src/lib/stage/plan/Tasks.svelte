<script lang="ts">
  import type Konva from 'konva';
  import { onMount, untrack } from 'svelte';
  import { SvelteSet } from 'svelte/reactivity';
  import { Group, Rect } from 'svelte-konva';

  import { hexWithAlpha } from '$lib/colors.svelte';
  import { type Instrument, type PlannedVolume, type Point2D } from '$lib/model';
  import { themes } from '$lib/themes/manager.svelte';
  import { pref, toastError } from '$lib/utils';

  import { getStageContext } from '../context.svelte';
  import { type Bounds, intersect, worldTransform } from '../geometry';
  import BoundsEditor from './BoundsEditor.svelte';
  import Path from './Path.svelte';
  import PointsEditor from './PointsEditor.svelte';
  import VolumeTooltip from './VolumeTooltip.svelte';

  interface Props {
    instrument: Instrument;
    editingTask?: string | null;
    fill?: (volume: PlannedVolume) => string | undefined;
  }

  let { instrument, editingTask = null, fill }: Props = $props();

  const context = getStageContext();
  const visibility = pref<Record<string, boolean>>('stage:task-visible', {});
  const taskVisible = (task: string) => visibility.get()[task] ?? true;
  const color = $derived(themes.resolvedMode === 'light' ? '#52525b' : '#d4d4d8');
  const disabled = $derived(instrument.mode === 'capture' || instrument.edits.busy);
  const selected = $derived(instrument.plan.find(({ id }) => id === editingTask));
  const taskOrder = $derived(new Map(instrument.plan.map(({ id }, index) => [id, index + 1])));
  const tiles = $derived.by(() => {
    const result: {
      order: number;
      key: string;
      task: string;
      taskOrder: number | undefined;
      bounds: Bounds;
      color: string | undefined;
    }[] = [];
    for (const [index, volume] of instrument.plannedVolumes.entries()) {
      const order = index + 1;
      const seen = new SvelteSet<string>();
      for (const footprint of Object.values(instrument.profileFovs[volume.profile] ?? {})) {
        const bounds = {
          minX: volume.x + footprint.min.x,
          minY: volume.y + footprint.min.y,
          maxX: volume.x + footprint.max.x,
          maxY: volume.y + footprint.max.y
        };
        if (!Object.values(bounds).every(Number.isFinite) || bounds.maxX <= bounds.minX || bounds.maxY <= bounds.minY)
          continue;
        const key = `${order}:${bounds.minX}:${bounds.minY}:${bounds.maxX}:${bounds.maxY}`;
        if (seen.has(key)) continue;
        seen.add(key);
        result.push({
          order,
          key,
          task: volume.task,
          taskOrder: taskOrder.get(volume.task),
          bounds,
          color: fill?.(volume)
        });
      }
    }
    return result;
  });
  const drawn = $derived(
    context.visibleBounds
      ? tiles.filter(({ task, bounds }) => taskVisible(task) && intersect(bounds, context.visibleBounds!))
      : []
  );
  const hovered = $derived.by(() => {
    const cursor = context.cursor;
    if (!context.interactionEnabled || !cursor || selected) return [];
    const seen = new SvelteSet<number>();
    return drawn.filter(({ order, bounds }) => {
      if (
        seen.has(order) ||
        cursor.x < bounds.minX ||
        cursor.x > bounds.maxX ||
        cursor.y < bounds.minY ||
        cursor.y > bounds.maxY
      )
        return false;
      seen.add(order);
      return true;
    });
  });
  const overVolumes = $derived(hovered.length > 0);
  const hoveredTasks = $derived(new SvelteSet(hovered.map(({ task }) => task)));
  let tooltipReady = $state(false);

  $effect(() => {
    tooltipReady = false;
    if (!overVolumes) return;
    const timer = setTimeout(() => (tooltipReady = true), 1000);
    return () => clearTimeout(timer);
  });

  export function destinations(hits: readonly Konva.Shape[]) {
    const orders = new Set(
      hits.flatMap((hit) =>
        hit
          .name()
          .split(/\s+/)
          .filter((name) => name.startsWith('volume:'))
          .map((name) => Number(name.slice('volume:'.length)))
      )
    );
    return instrument.plannedVolumes.flatMap((volume, index) =>
      orders.has(index + 1)
        ? [
            {
              order: index + 1,
              task: volume.task,
              taskOrder: taskOrder.get(volume.task),
              profile: volume.profile,
              point: { x: volume.x, y: volume.y }
            }
          ]
        : []
    );
  }

  export function extent(): Bounds | null {
    let result: Bounds | null = null;
    for (const { bounds, task } of tiles) {
      if (!taskVisible(task)) continue;
      result = result
        ? {
            minX: Math.min(result.minX, bounds.minX),
            minY: Math.min(result.minY, bounds.minY),
            maxX: Math.max(result.maxX, bounds.maxX),
            maxY: Math.max(result.maxY, bounds.maxY)
          }
        : bounds;
    }
    return result;
  }

  onMount(() =>
    context.registerMenuSource({
      id: 'task-volumes',
      goTo: (selection) =>
        destinations(selection.hits).map((volume) => ({
          id: `volume:${volume.order}`,
          label: `Volume ${volume.order}`,
          point: volume.point
        })),
      fit: () => {
        const bounds = extent();
        return bounds ? [{ id: 'tasks', label: 'Tasks', bounds }] : [];
      }
    })
  );

  $effect(() => {
    const tasks = instrument.plan.map(({ id }, index) => ({ id, index }));
    const unregister = untrack(() =>
      tasks.map((task) =>
        context.register({
          id: `task:${task.id}`,
          label: `Task ${task.index + 1}`,
          menuOrder: 1 + task.index / Math.max(1, tasks.length),
          get visible() {
            return taskVisible(task.id);
          },
          setVisible: (visible) => visibility.set({ ...visibility.get(), [task.id]: visible })
        })
      )
    );
    return () => untrack(() => unregister.forEach((remove) => remove()));
  });

  function updateGeometry(taskId: string, points: Point2D[]): void {
    if (instrument.mode === 'capture') return;
    const current = instrument.plan.find(({ id }) => id === taskId);
    if (current) toastError(instrument.updateTask(taskId, { xy: { ...current.xy, points } }));
  }
</script>

<Group {...worldTransform(context.view.scale, context.orientation)}>
  {#each drawn as tile (tile.key)}
    {@const active = tile.task === editingTask}
    {@const subdued = editingTask !== null && !active && !hoveredTasks.has(tile.task)}
    <Rect
      staticConfig
      x={tile.bounds.minX}
      y={tile.bounds.minY}
      width={tile.bounds.maxX - tile.bounds.minX}
      height={tile.bounds.maxY - tile.bounds.minY}
      name={`volume:${tile.order}`}
      fill={hexWithAlpha(tile.color ?? color, subdued ? (tile.color ? 0.08 : 0.02) : tile.color ? 0.12 : 0.03)}
      stroke={hexWithAlpha(tile.color ?? color, subdued ? 0.16 : active ? 0.4 : 0.25)}
      strokeWidth={1}
      strokeScaleEnabled={false}
      perfectDrawEnabled={false}
      shadowForStrokeEnabled={false}
    />
  {/each}
  <Path volumes={instrument.plannedVolumes} {taskVisible} {color} />
</Group>

{#if selected}
  {#key selected.id}
    {#if selected.xy.mode === 'bounding_box'}
      <BoundsEditor
        geometry={selected.xy}
        {disabled}
        {color}
        oncommit={(points) => updateGeometry(selected.id, points)}
      />
    {:else}
      <PointsEditor
        geometry={selected.xy}
        {disabled}
        {color}
        oncommit={(points) => updateGeometry(selected.id, points)}
      />
    {/if}
  {/key}
{/if}

{#if tooltipReady && hovered.length}
  <VolumeTooltip volumes={hovered} />
{/if}
