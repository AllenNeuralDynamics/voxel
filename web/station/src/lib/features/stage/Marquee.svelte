<script lang="ts">
  import type Konva from 'konva';
  import { Group, Line, Rect } from 'svelte-konva';

  import { Plane } from './context';
  import { type Bounds, Geometry } from './geometry';

  type Edge = 'minX' | 'maxX' | 'minY' | 'maxY';

  let { bounds = $bindable() }: { bounds: Bounds } = $props();

  const plane = Plane.get();
  let hovered = $state<Edge | null>(null);
  let resizing = $state<Edge | null>(null);
  let pointerId: number | null = null;
  const rect = $derived(Geometry.screenRect(bounds, plane.view));
  const edges = $derived([
    { edge: 'minX' as const, cursor: 'ew-resize', points: [rect.x, rect.y, rect.x, rect.y + rect.height] },
    {
      edge: 'maxX' as const,
      cursor: 'ew-resize',
      points: [rect.x + rect.width, rect.y, rect.x + rect.width, rect.y + rect.height]
    },
    { edge: 'maxY' as const, cursor: 'ns-resize', points: [rect.x, rect.y, rect.x + rect.width, rect.y] },
    {
      edge: 'minY' as const,
      cursor: 'ns-resize',
      points: [rect.x, rect.y + rect.height, rect.x + rect.width, rect.y + rect.height]
    }
  ]);

  function start(edge: Edge, event: Konva.KonvaEventObject<PointerEvent>) {
    if (event.evt.button !== 0) return;
    event.cancelBubble = true;
    event.evt.preventDefault();
    hovered = resizing = edge;
    pointerId = event.evt.pointerId;
  }

  function move(event: PointerEvent) {
    const edge = resizing;
    if (!edge || event.pointerId !== pointerId) return;
    const point = plane.fromClient(event.clientX, event.clientY);
    const limits = plane.bounds;
    const value =
      edge === 'minX'
        ? Math.max(limits.minX, Math.min(point.x, bounds.maxX))
        : edge === 'maxX'
          ? Math.min(limits.maxX, Math.max(point.x, bounds.minX))
          : edge === 'minY'
            ? Math.max(limits.minY, Math.min(point.y, bounds.maxY))
            : Math.min(limits.maxY, Math.max(point.y, bounds.minY));
    bounds = { ...bounds, [edge]: value };
  }

  function finish(event?: PointerEvent) {
    if (!resizing || (event && event.pointerId !== pointerId)) return;
    resizing = null;
    pointerId = null;
    hovered = null;
    plane.setCursor(plane.altHeld ? 'crosshair' : 'grab');
  }
</script>

<svelte:window onblur={() => finish()} onpointermove={move} onpointerup={finish} onpointercancel={finish} />

<Group {...Geometry.screen(plane.view)}>
  <Rect {...rect} fill={plane.colors.accent} opacity={0.08} listening={false} />
  {#each edges as { edge, cursor, points } (edge)}
    <Line
      {points}
      stroke={plane.colors.accent}
      strokeWidth={hovered === edge ? 2 : 1.5}
      dash={[4, 3]}
      hitStrokeWidth={10}
      perfectDrawEnabled={false}
      onpointerenter={() => {
        hovered = edge;
        plane.setCursor(cursor);
      }}
      onpointerleave={() => {
        if (resizing) return;
        hovered = null;
        plane.setCursor(plane.altHeld ? 'crosshair' : 'grab');
      }}
      onpointerdown={(event) => start(edge, event)}
      onpointerclick={(event) => (event.cancelBubble = true)}
    />
  {/each}
</Group>
