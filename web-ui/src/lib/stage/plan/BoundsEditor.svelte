<script lang="ts">
  import type Konva from 'konva';
  import { Circle, Group, Line } from 'svelte-konva';

  import { hexWithAlpha } from '$lib/colors.svelte';
  import { type Point2D, pointBounds, rectanglePoints, resizePointsToBounds, type XYDefinition } from '$lib/model';

  import { getStageContext } from '../context.svelte';
  import { type Bounds, screenTransform, worldTransform } from '../geometry';

  type DragEvent = Konva.KonvaEventObject<MouseEvent | PointerEvent | TouchEvent>;
  type Handle = 'edge' | 'corner';
  const handles = [0, 1, 2, 3] as const;
  const minSize = 1e-6;

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
  let hoveredEdge = $state<number | null>(null);
  let hoveredCorner = $state<number | null>(null);
  let dragging = $state.raw<{ kind: Handle; index: number; bounds: Bounds; source: Point2D[] } | null>(null);
  const bounds = $derived(dragging?.bounds ?? pointBounds(geometry.points));
  const corners = $derived(rectanglePoints(bounds));

  function begin(kind: Handle, index: number): void {
    dragging = { kind, index, bounds: { ...bounds }, source: geometry.points.map((point) => ({ ...point })) };
  }

  function move(kind: Handle, index: number, event: DragEvent): void {
    if (!dragging || dragging.kind !== kind || dragging.index !== index) return;
    const pointer =
      kind === 'corner' ? event.target.getAbsolutePosition() : event.target.getStage()?.getPointerPosition();
    if (!pointer) return;
    const point = context.unproject(pointer);
    const next = { ...dragging.bounds };
    if (kind === 'edge') {
      if (index === 0) next.minY = Math.min(point.y, next.maxY - minSize);
      else if (index === 1) next.maxX = Math.max(point.x, next.minX + minSize);
      else if (index === 2) next.maxY = Math.max(point.y, next.minY + minSize);
      else next.minX = Math.min(point.x, next.maxX - minSize);
      event.target.position({ x: 0, y: 0 });
    } else {
      if (index === 0 || index === 3) next.minX = Math.min(point.x, next.maxX - minSize);
      else next.maxX = Math.max(point.x, next.minX + minSize);
      if (index === 0 || index === 1) next.minY = Math.min(point.y, next.maxY - minSize);
      else next.maxY = Math.max(point.y, next.minY + minSize);
    }
    dragging = { ...dragging, bounds: next };
  }

  function finish(kind: Handle, index: number, event: DragEvent): void {
    if (!dragging || dragging.kind !== kind || dragging.index !== index) return;
    move(kind, index, event);
    const edit = dragging;
    const original = pointBounds(edit.source);
    dragging = null;
    if (kind === 'edge') event.target.position({ x: 0, y: 0 });
    event.target.getStage()!.container().style.cursor = 'grab';
    if (
      original.minX !== edit.bounds.minX ||
      original.minY !== edit.bounds.minY ||
      original.maxX !== edit.bounds.maxX ||
      original.maxY !== edit.bounds.maxY
    )
      oncommit?.(resizePointsToBounds(edit.source, edit.bounds));
  }
</script>

<Group {...worldTransform(context.view.scale, context.orientation)}>
  <Line
    points={corners.flatMap(({ x, y }) => [x, y])}
    closed
    stroke={hexWithAlpha(color, 0.72)}
    strokeWidth={1.25}
    strokeScaleEnabled={false}
    listening={false}
  />
  {#each handles as index (index)}
    {@const first = corners[index]}
    {@const second = corners[(index + 1) % corners.length]}
    <Line
      name="task-geometry"
      points={[first.x, first.y, second.x, second.y]}
      stroke={hoveredEdge === index ? hexWithAlpha(color, 0.75) : hexWithAlpha(color, 0.001)}
      strokeWidth={hoveredEdge === index ? 2 : 1}
      hitStrokeWidth={12}
      strokeScaleEnabled={false}
      draggable={canEdit}
      dragDistance={4}
      onmouseenter={(event) => {
        hoveredEdge = index;
        if (canEdit) event.target.getStage()!.container().style.cursor = index % 2 === 0 ? 'ns-resize' : 'ew-resize';
      }}
      onmouseleave={(event) => {
        if (hoveredEdge === index) hoveredEdge = null;
        if (!dragging) event.target.getStage()!.container().style.cursor = 'grab';
      }}
      ondragstart={() => begin('edge', index)}
      ondragmove={(event) => move('edge', index, event)}
      ondragend={(event) => finish('edge', index, event)}
    />
  {/each}
</Group>

<Group {...screenTransform(context.view)}>
  {#each corners as corner, index (index)}
    {@const screen = context.project(corner)}
    {@const active = hoveredCorner === index || (dragging?.kind === 'corner' && dragging.index === index)}
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
        hoveredCorner = index;
        if (canEdit) event.target.getStage()!.container().style.cursor = 'move';
      }}
      onmouseleave={(event) => {
        if (hoveredCorner === index) hoveredCorner = null;
        if (!dragging) event.target.getStage()!.container().style.cursor = 'grab';
      }}
      ondragstart={() => begin('corner', index)}
      ondragmove={(event) => move('corner', index, event)}
      ondragend={(event) => finish('corner', index, event)}
    />
  {/each}
</Group>
