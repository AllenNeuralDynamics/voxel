<script lang="ts">
  import type Konva from 'konva';
  import { Group, Line, Rect } from 'svelte-konva';

  import type { Point as TaskPoint } from '$lib/core/spim.svelte';
  import type { SpecimenAxis } from '$lib/core/types';

  import { Plane } from './context';
  import { type Bounds, Geometry } from './geometry';

  type Key = 'nw' | 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w';

  interface Props {
    /** The box's 2 corners, on the map's 2 axes. */
    points: TaskPoint[];
    axes: [SpecimenAxis, SpecimenAxis];
    editable?: boolean;
    oncommit?: (points: TaskPoint[]) => void;
  }

  let { points, axes, editable = false, oncommit }: Props = $props();

  const KEYS: Key[] = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'];
  const CURSORS: Record<Key, string> = {
    nw: 'nwse-resize',
    se: 'nwse-resize',
    ne: 'nesw-resize',
    sw: 'nesw-resize',
    n: 'ns-resize',
    s: 'ns-resize',
    e: 'ew-resize',
    w: 'ew-resize'
  };
  const MIN_UM = 1;

  const plane = Plane.get();
  const [h, v] = $derived(axes);
  const canEdit = $derived(editable && plane.interactionEnabled);
  let dragging = $state.raw<Bounds | null>(null);
  const saved = $derived(
    Geometry.around(points.map((point) => ({ x: point[h] ?? 0, y: point[v] ?? 0 }))) ?? {
      minX: 0,
      minY: 0,
      maxX: 0,
      maxY: 0
    }
  );
  const bounds = $derived(dragging ?? saved);

  function handleAt(key: Key, box: Bounds) {
    const x = key.includes('w') ? box.minX : key.includes('e') ? box.maxX : (box.minX + box.maxX) / 2;
    const y = key.includes('n') ? box.maxY : key.includes('s') ? box.minY : (box.minY + box.maxY) / 2;
    return plane.project({ x, y });
  }

  function move(key: Key, event: Konva.KonvaEventObject<MouseEvent | PointerEvent | TouchEvent>) {
    const node = event.target;
    const point = plane.unproject({ x: node.x() + 4, y: node.y() + 4 });
    const next = { ...(dragging ?? saved) };
    if (key.includes('w')) next.minX = Math.min(point.x, next.maxX - MIN_UM);
    if (key.includes('e')) next.maxX = Math.max(point.x, next.minX + MIN_UM);
    if (key.includes('s')) next.minY = Math.min(point.y, next.maxY - MIN_UM);
    if (key.includes('n')) next.maxY = Math.max(point.y, next.minY + MIN_UM);
    dragging = next;
  }

  function finish(key: Key, event: Konva.KonvaEventObject<MouseEvent | PointerEvent | TouchEvent>) {
    move(key, event);
    const edit = dragging;
    dragging = null;
    plane.setCursor('grab');
    if (
      !edit ||
      (edit.minX === saved.minX && edit.minY === saved.minY && edit.maxX === saved.maxX && edit.maxY === saved.maxY)
    )
      return;
    oncommit?.([
      { [h]: edit.minX, [v]: edit.minY },
      { [h]: edit.maxX, [v]: edit.maxY }
    ]);
  }
</script>

<Group {...Geometry.world(plane.view.scale)} listening={false}>
  <Line
    points={[bounds.minX, bounds.minY, bounds.maxX, bounds.minY, bounds.maxX, bounds.maxY, bounds.minX, bounds.maxY]}
    closed
    stroke={plane.colors.accent}
    strokeWidth={1.5}
    dash={[4, 3]}
    strokeScaleEnabled={false}
  />
</Group>

{#if editable}
  <Group {...Geometry.screen(plane.view)}>
    {#each KEYS as key (key)}
      {@const at = handleAt(key, bounds)}
      <Rect
        name="task-handle"
        x={at.x - 4}
        y={at.y - 4}
        width={8}
        height={8}
        fill={plane.colors.floating}
        stroke={plane.colors.accent}
        strokeWidth={1.5}
        draggable={canEdit}
        dragDistance={2}
        onpointerenter={() => canEdit && plane.setCursor(CURSORS[key])}
        onpointerleave={() => !dragging && plane.setCursor('grab')}
        onpointerclick={(event) => (event.cancelBubble = true)}
        ondragstart={(event) => (event.cancelBubble = true)}
        ondragmove={(event) => move(key, event)}
        ondragend={(event) => finish(key, event)}
      />
    {/each}
  </Group>
{/if}
