<script lang="ts">
  import { onMount } from 'svelte';
  import { Circle, Group, Line, Text } from 'svelte-konva';

  import { Prefs } from '$lib/core/prefs';
  import type { Point as TaskPoint, SpimTask } from '$lib/core/spim.svelte';
  import { hexWithAlpha } from '@voxel/kit/colors';

  import BoundsEditor from './BoundsEditor.svelte';
  import { Plane } from './context';
  import { Geometry, type Point } from './geometry';
  import Path from './Path.svelte';
  import PointsEditor from './PointsEditor.svelte';
  import type { StagePlan, Tile } from './stage-plan.svelte';

  interface Props {
    plan: StagePlan;
    tasks: SpimTask[];
    selected?: string;
    /** The volume that runs now, and whether a run is on: earlier volumes are done. */
    progress?: { visit: number } | null;
    editable?: boolean;
    hovered?: Tile | null;
    onoutline?: (task: SpimTask, points: TaskPoint[]) => void;
  }

  let {
    plan,
    tasks,
    selected,
    progress = null,
    editable = false,
    hovered = $bindable(null),
    onoutline
  }: Props = $props();

  const plane = Plane.get();
  const accent = $derived(plane.colors.accent);
  const visible = $derived(Prefs.stageTasks.get());
  const colorBy = $derived(Prefs.tileColors.get());
  // Auto shows task status while a run goes, and zones at other times.
  const byZone = $derived(plan.zones.length > 1 && (colorBy === 'zones' || (colorBy === 'auto' && progress === null)));

  $effect(() => {
    if (plan.zones.length < 2) return;
    return plane.register({
      id: 'tile-colors',
      label: 'Tile colors',
      menuOrder: 10,
      submenu: true,
      choices: [
        { value: 'auto', label: 'Auto' },
        { value: 'status', label: 'Task status' },
        { value: 'zones', label: 'Zones' }
      ],
      get value() {
        return colorBy;
      },
      setValue: (value) => Prefs.tileColors.set(value as typeof colorBy)
    });
  });

  /** The tasks under the menu's point, from the names of the tiles there. */
  function under(names: string[]): string[] {
    return [...new Set(names.filter((name) => name.startsWith('task:')).map((name) => name.slice('task:'.length)))];
  }

  onMount(() => {
    const layer = plane.register({
      id: 'tasks',
      label: 'Tasks',
      menuOrder: 1,
      get visible() {
        return visible;
      },
      setVisible: (value) => Prefs.stageTasks.set(value)
    });
    const source = plane.registerMenuSource({
      id: 'task-volumes',
      goTo: ({ names }) => {
        const stops = new Set(names.filter((name) => name.startsWith('stop:')));
        const tasksThere = under(names);
        const indexes = plan.tiles
          .filter((tile) => tasksThere.includes(tile.task) && stops.has(`stop:${tile.stop}`))
          .flatMap((tile) => tile.volumes);
        return [...new Set(indexes)]
          .sort((a, b) => a - b)
          .flatMap((index) => {
            const point = plan.volumePoint(index);
            const volume = plan.volumes[index];
            return point && volume
              ? [{ id: `volume:${index}`, label: `Volume ${index + 1} · ${volume.task}, ${volume.profile}`, point }]
              : [];
          });
      },
      fit: ({ names }) => {
        const all = plan.taskBounds();
        if (!all) return [];
        const ids = under(names);
        if (selected && !ids.includes(selected)) ids.push(selected);
        return [
          { id: 'tasks', label: 'All', bounds: all, group: 'Tasks' },
          ...ids.flatMap((id) => {
            const bounds = plan.taskBounds(id);
            return bounds ? [{ id: `task:${id}`, label: id, bounds, group: 'Tasks' }] : [];
          })
        ];
      }
    });
    return () => {
      layer();
      source();
    };
  });
  const drawn = $derived(
    plane.visibleBounds ? plan.tiles.filter((tile) => Geometry.intersect(tile.bounds, plane.visibleBounds!)) : []
  );
  const task = $derived(tasks.find((candidate) => candidate.id === selected));
  const ownPath = $derived.by(() => {
    if (!selected) return [];
    const centers: Point[] = [];
    for (const tile of plan.tiles) {
      if (tile.task !== selected || centers.length > tile.stop) continue;
      centers.push(tile.center);
    }
    return centers;
  });
  // A name sits on its task's highest tile, not the box corner, which is empty space for scattered points. It shows
  // when it fits, and always on the selected or hovered task.
  const labels = $derived.by(() =>
    tasks.flatMap((candidate) => {
      const bounds = plan.taskBounds(candidate.id);
      if (!bounds) return [];
      const wide = (bounds.maxX - bounds.minX) * plane.view.scale;
      const shown = candidate.id === selected || candidate.id === hovered?.task || wide >= candidate.id.length * 7 + 4;
      const top = plan.tiles
        .filter((tile) => tile.task === candidate.id)
        .reduce((best, tile) =>
          tile.bounds.maxY > best.bounds.maxY ||
          (tile.bounds.maxY === best.bounds.maxY && tile.bounds.minX < best.bounds.minX)
            ? tile
            : best
        );
      return shown ? [{ id: candidate.id, at: plane.project({ x: top.bounds.minX, y: top.bounds.maxY }) }] : [];
    })
  );

  function lookOf(tile: Tile): { fill: string; stroke: string; width: number } {
    const now = progress !== null && tile.volumes.includes(progress.visit);
    const done = progress !== null && tile.volumes.length > 0 && tile.volumes.every((v) => v < progress!.visit);
    const on = tile.task === selected;
    const over = tile.task === hovered?.task;
    const zone = byZone ? plan.zoneOf(tile.devices) : undefined;
    if (zone) {
      const color = plane.colors.zones[zone.index % plane.colors.zones.length];
      return {
        fill: hexWithAlpha(color, on ? 0.38 : over ? 0.32 : 0.26),
        stroke: now ? plane.colors.fg : on ? color : hexWithAlpha(color, 0.7),
        width: now ? 2.5 : 1
      };
    }
    const fill = done ? 0.16 : over ? 0.08 : on ? 0.06 : 0;
    return {
      fill: fill > 0 ? hexWithAlpha(accent, fill) : 'transparent',
      stroke: now ? accent : hexWithAlpha(accent, on ? 0.5 : 0.22),
      width: now ? 2.5 : 1
    };
  }
</script>

<Group {...Geometry.world(plane.view.scale)}>
  {#each visible ? drawn : [] as tile (tile.key)}
    {@const look = lookOf(tile)}
    <Line
      points={tile.points.flatMap((point) => [point.x, point.y])}
      closed
      name={`task:${tile.task} stop:${tile.stop}`}
      fill={look.fill}
      stroke={look.stroke}
      strokeWidth={look.width}
      strokeScaleEnabled={false}
      perfectDrawEnabled={false}
      shadowForStrokeEnabled={false}
      onpointerenter={() => {
        if (plane.interactionEnabled) hovered = tile;
      }}
      onpointerleave={() => {
        if (hovered?.key === tile.key) hovered = null;
      }}
    />
  {/each}
  <Path {plan} {tasks} color={plane.colors.fgFaint} />
</Group>

{#if ownPath.length > 1}
  <Group {...Geometry.screen(plane.view)} listening={false}>
    <Line
      points={ownPath.flatMap((point) => {
        const at = plane.project(point);
        return [at.x, at.y];
      })}
      stroke={plane.colors.fgFaint}
      strokeWidth={1}
    />
    {#each ownPath as point, index (index)}
      {@const at = plane.project(point)}
      <Circle
        x={at.x}
        y={at.y}
        radius={index === 0 ? 4 : 2}
        fill={index === 0 ? plane.colors.fgMuted : plane.colors.fgFaint}
      />
    {/each}
  </Group>
{/if}

<Group {...Geometry.screen(plane.view)} listening={false}>
  {#each labels as label (label.id)}
    <Text
      x={label.at.x}
      y={label.at.y - 17}
      text={label.id}
      fontSize={12}
      fontStyle="500"
      fontFamily="IBM Plex Sans, ui-sans-serif, system-ui, sans-serif"
      fill={label.id === selected ? accent : plane.colors.fgMuted}
    />
  {/each}
</Group>

{#if task && plan.outlinesShown}
  {#key task.id}
    {#if task.region.outline.kind === 'bounding_box'}
      <BoundsEditor
        points={task.region.outline.points}
        axes={[plan.axes.h, plan.axes.v]}
        {editable}
        oncommit={(points) => onoutline?.(task, points)}
      />
    {:else}
      <PointsEditor
        points={task.region.outline.points}
        axes={[plan.axes.h, plan.axes.v]}
        hull={task.region.outline.kind === 'convex_hull'}
        {editable}
        oncommit={(points) => onoutline?.(task, points)}
      />
    {/if}
  {/key}
{/if}
