<script lang="ts">
  import type Konva from 'konva';
  import { Circle, Group, Line } from 'svelte-konva';

  import { hexWithAlpha } from '$lib/colors.svelte';
  import { convexHull, type Point2D, type XYDefinition } from '$lib/model';

  import { getStageContext } from '../context.svelte';
  import { screenTransform, worldTransform } from '../geometry';

  type DragEvent = Konva.KonvaEventObject<MouseEvent | PointerEvent | TouchEvent>;

  let {
    geometry,
    disabled = false,
    color,
    oncommit
  }: {
    geometry: XYDefinition;
    disabled?: boolean;
    color: string;
    oncommit?: (points: Point2D[]) => void;
  } = $props();

  const context = getStageContext();
  const canEdit = $derived(!disabled && !!oncommit && context.interactionEnabled);
  let hovered = $state<number | null>(null);
  let dragging = $state.raw<{ index: number; points: Point2D[] } | null>(null);
  const points = $derived(dragging?.points ?? geometry.points);
  const boundary = $derived(geometry.mode === 'convex_hull' ? convexHull(points) : []);

  function begin(index: number, event: DragEvent): void {
    dragging = { index, points: geometry.points.map((point) => ({ ...point })) };
    event.target.getStage()!.container().style.cursor = 'move';
  }

  function move(index: number, event: DragEvent): void {
    if (!dragging || dragging.index !== index) return;
    const point = context.unproject(event.target.getAbsolutePosition());
    const next = dragging.points.map((current, i) => (i === index ? point : current));
    const duplicate = next.some((current, i) => i !== index && current.x === point.x && current.y === point.y);
    if (duplicate || (geometry.mode === 'convex_hull' && convexHull(next).length < 3)) {
      event.target.position(context.project(dragging.points[index]));
      return;
    }
    dragging = { index, points: next };
  }

  function finish(index: number, event: DragEvent): void {
    if (!dragging || dragging.index !== index) return;
    move(index, event);
    const edited = dragging.points;
    dragging = null;
    event.target.getStage()!.container().style.cursor = 'grab';
    if (edited.some((point, i) => point.x !== geometry.points[i].x || point.y !== geometry.points[i].y))
      oncommit?.(edited);
  }
</script>

{#if geometry.mode === 'convex_hull' && boundary.length >= 3}
  <Group {...worldTransform(context.view.scale, context.orientation)}>
    <Line
      points={boundary.flatMap(({ x, y }) => [x, y])}
      closed
      stroke={hexWithAlpha(color, 0.72)}
      strokeWidth={1.25}
      strokeScaleEnabled={false}
      listening={false}
    />
  </Group>
{/if}

<Group {...screenTransform(context.view)}>
  {#each points as point, index (index)}
    {@const screen = context.project(point)}
    {@const active = hovered === index || dragging?.index === index}
    <Circle
      name="task-geometry"
      x={Math.round(screen.x)}
      y={Math.round(screen.y)}
      radius={3}
      fill={active ? color : hexWithAlpha(color, 0.62)}
      hitStrokeWidth={6}
      perfectDrawEnabled={false}
      draggable={canEdit}
      dragDistance={4}
      onmouseenter={(event) => {
        hovered = index;
        if (canEdit) event.target.getStage()!.container().style.cursor = 'move';
      }}
      onmouseleave={(event) => {
        if (hovered === index) hovered = null;
        if (!dragging) event.target.getStage()!.container().style.cursor = 'grab';
      }}
      ondragstart={(event) => begin(index, event)}
      ondragmove={(event) => move(index, event)}
      ondragend={(event) => finish(index, event)}
    />
  {/each}
</Group>
