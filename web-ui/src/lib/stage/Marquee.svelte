<script module lang="ts">
  export type MarqueeEdge = 'minX' | 'maxX' | 'minY' | 'maxY';
</script>

<script lang="ts">
  import type Konva from 'konva';
  import { Group, Line, Rect } from 'svelte-konva';

  import { watchTheme } from '$lib/themes/manager.svelte';

  import { getStageContext } from './context.svelte';
  import { type Bounds, screenRect, screenTransform } from './geometry';

  let { bounds = $bindable() }: { bounds: Bounds } = $props();

  const context = getStageContext();
  let group = $state<Group>();
  let color = $state('#e5e7eb');
  let hovered = $state<MarqueeEdge | null>(null);
  let resizing = $state<MarqueeEdge | null>(null);
  let pointerId: number | null = null;
  const rect = $derived(screenRect(bounds, context.view, context.orientation));
  const edges = $derived([
    {
      edge: context.orientation.x > 0 ? ('minX' as const) : ('maxX' as const),
      cursor: 'ew-resize',
      points: [rect.x, rect.y, rect.x, rect.y + rect.height]
    },
    {
      edge: context.orientation.x > 0 ? ('maxX' as const) : ('minX' as const),
      cursor: 'ew-resize',
      points: [rect.x + rect.width, rect.y, rect.x + rect.width, rect.y + rect.height]
    },
    {
      edge: context.orientation.y > 0 ? ('maxY' as const) : ('minY' as const),
      cursor: 'ns-resize',
      points: [rect.x, rect.y, rect.x + rect.width, rect.y]
    },
    {
      edge: context.orientation.y > 0 ? ('minY' as const) : ('maxY' as const),
      cursor: 'ns-resize',
      points: [rect.x, rect.y + rect.height, rect.x + rect.width, rect.y + rect.height]
    }
  ]);

  function setCursor(cursor: string) {
    const container = group?.node.getStage()?.container();
    if (container) container.style.cursor = cursor;
  }

  function enter(edge: MarqueeEdge, cursor: string) {
    hovered = edge;
    setCursor(cursor);
  }

  function leave() {
    if (resizing) return;
    hovered = null;
    setCursor(context.altHeld ? 'crosshair' : 'grab');
  }

  function start(edge: MarqueeEdge, event: Konva.KonvaEventObject<PointerEvent>) {
    if (event.evt.button !== 0) return;
    event.cancelBubble = true;
    event.evt.preventDefault();
    hovered = resizing = edge;
    pointerId = event.evt.pointerId;
  }

  function move(event: PointerEvent) {
    const edge = resizing;
    const container = group?.node.getStage()?.container();
    if (!edge || event.pointerId !== pointerId || !container) return;
    const frame = container.getBoundingClientRect();
    const point = context.unproject({ x: event.clientX - frame.left, y: event.clientY - frame.top });
    const limits = context.bounds;
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
    setCursor(context.altHeld ? 'crosshair' : 'grab');
  }

  watchTheme(() => {
    const container = group?.node.getStage()?.container();
    if (container) color = getComputedStyle(container).getPropertyValue('--color-fg').trim() || color;
  });
</script>

<svelte:window onblur={() => finish()} onpointermove={move} onpointerup={finish} onpointercancel={finish} />

<Group bind:this={group} {...screenTransform(context.view)}>
  <Rect {...rect} fill={color} opacity={0.08} listening={false} />
  {#each edges as { edge, cursor, points } (edge)}
    <Line
      {points}
      stroke={color}
      strokeWidth={hovered === edge ? 1.5 : 1}
      dash={[4, 3]}
      hitStrokeWidth={10}
      perfectDrawEnabled={false}
      onpointerenter={() => enter(edge, cursor)}
      onpointerleave={leave}
      onpointerdown={(event) => start(edge, event)}
      onpointerclick={(event) => (event.cancelBubble = true)}
    />
  {/each}
</Group>
