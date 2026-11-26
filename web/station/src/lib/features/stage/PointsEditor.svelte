<script lang="ts">
  import type Konva from 'konva';
  import { Circle, Group, Line } from 'svelte-konva';

  import type { Point as TaskPoint } from '$lib/core/spim.svelte';
  import type { SpecimenAxis } from '$lib/core/types';

  import { Plane } from './context';
  import { Geometry, type Point } from './geometry';

  interface Props {
    /** The outline's points, on the map's 2 axes. */
    points: TaskPoint[];
    axes: [SpecimenAxis, SpecimenAxis];
    /** Draws the hull through the points. */
    hull?: boolean;
    editable?: boolean;
    oncommit?: (points: TaskPoint[]) => void;
  }

  let { points, axes, hull = false, editable = false, oncommit }: Props = $props();

  const plane = Plane.get();
  const [h, v] = $derived(axes);
  const canEdit = $derived(editable && plane.interactionEnabled);
  let dragging = $state.raw<{ index: number; points: Point[] } | null>(null);
  const saved = $derived(points.map((point) => ({ x: point[h] ?? 0, y: point[v] ?? 0 })));
  const shown = $derived(dragging?.points ?? saved);
  const boundary = $derived(hull ? Geometry.hull(shown) : []);

  function move(index: number, event: Konva.KonvaEventObject<MouseEvent | PointerEvent | TouchEvent>) {
    const point = plane.unproject({ x: event.target.x(), y: event.target.y() });
    const base = dragging?.points ?? saved;
    const next = base.map((current, i) => (i === index ? point : current));
    if (hull && Geometry.hull(next).length < 3) return;
    dragging = { index, points: next };
  }

  function finish(index: number, event: Konva.KonvaEventObject<MouseEvent | PointerEvent | TouchEvent>) {
    move(index, event);
    const edited = dragging?.points;
    dragging = null;
    plane.setCursor('grab');
    if (!edited || edited.every((point, i) => point.x === saved[i].x && point.y === saved[i].y)) return;
    oncommit?.(edited.map((point) => ({ [h]: point.x, [v]: point.y })));
  }
</script>

{#if boundary.length >= 3}
  <Group {...Geometry.world(plane.view.scale)} listening={false}>
    <Line
      points={boundary.flatMap(({ x, y }) => [x, y])}
      closed
      stroke={plane.colors.accent}
      strokeWidth={1.5}
      dash={[4, 3]}
      strokeScaleEnabled={false}
    />
  </Group>
{/if}

<Group {...Geometry.screen(plane.view)}>
  {#each shown as point, index (index)}
    {@const at = plane.project(point)}
    <Circle
      name="task-handle"
      x={at.x}
      y={at.y}
      radius={5}
      fill={plane.colors.floating}
      stroke={plane.colors.accent}
      strokeWidth={1.5}
      listening={editable}
      draggable={canEdit}
      dragDistance={2}
      onpointerenter={() => canEdit && plane.setCursor('move')}
      onpointerleave={() => !dragging && plane.setCursor('grab')}
      onpointerclick={(event) => (event.cancelBubble = true)}
      ondragstart={(event) => (event.cancelBubble = true)}
      ondragmove={(event) => move(index, event)}
      ondragend={(event) => finish(index, event)}
    />
  {/each}
</Group>
