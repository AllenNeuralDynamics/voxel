<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import { Circle, Group, Line, Rect } from 'svelte-konva';

  import { Plane } from './context';
  import { Geometry, type Point } from './geometry';

  interface Props {
    position: Point | null;
    /** The size of 1 capture of the active profile on the map's axes, in µm; 0 on the scan axis. */
    frame: { width: number; height: number } | null;
    /** Where a move sent the stage, while it is not there yet. */
    target?: Point | null;
    oncenter?: () => void;
  }

  let { position, frame, target = null, oncenter }: Props = $props();

  const plane = Plane.get();
  const stroke = $derived(plane.colors.marks);
  let grid = $state<{ origin: Point; width: number; height: number } | null>(null);

  // The grid starts where the stage is when Alt goes down, and stays while the menu is open.
  $effect(() => {
    if (!plane.altHeld && !plane.menuSelection) grid = null;
    else if (plane.altHeld && !plane.menuSelection && !grid) {
      grid = untrack(() =>
        position && frame && frame.width > 0 && frame.height > 0 ? { origin: { ...position }, ...frame } : null
      );
    }
  });

  /** The middle of the grid cell under `point`, while the grid shows. */
  export function cell(point: Point): Point | undefined {
    if (!grid || !Geometry.contains(plane.bounds, point)) return undefined;
    return {
      x: grid.origin.x + Math.round((point.x - grid.origin.x) / grid.width) * grid.width,
      y: grid.origin.y + Math.round((point.y - grid.origin.y) / grid.height) * grid.height
    };
  }

  function cellTarget(point: Point) {
    const at = cell(point);
    return at && grid
      ? [{ id: 'grid-cell', label: 'Grid cell', point: at, size: { width: grid.width, height: grid.height } }]
      : [];
  }

  onMount(() =>
    plane.registerMenuSource({
      id: 'position-grid',
      addTask: ({ point }) => cellTarget(point),
      goTo: ({ point }) => cellTarget(point)
    })
  );

  const highlighted = $derived.by(() => {
    if (plane.menuSelection) return plane.menuPreview;
    const point = plane.cursor;
    if (!grid || !point || plane.selecting || (plane.marquee && Geometry.contains(plane.marquee, point))) return null;
    return cell(point) ?? null;
  });
  const footprint = $derived(grid ?? frame);
  const gridLines = $derived.by(() => {
    const bounds = plane.visibleBounds && Geometry.intersect(plane.visibleBounds, plane.bounds);
    if (!grid || !bounds) return [];
    const lines: number[][] = [];
    const left = grid.origin.x - grid.width / 2;
    const bottom = grid.origin.y - grid.height / 2;
    for (let i = Math.ceil((bounds.minX - left) / grid.width); i <= Math.floor((bounds.maxX - left) / grid.width); i++)
      lines.push([left + i * grid.width, bounds.minY, left + i * grid.width, bounds.maxY]);
    for (
      let i = Math.ceil((bounds.minY - bottom) / grid.height);
      i <= Math.floor((bounds.maxY - bottom) / grid.height);
      i++
    )
      lines.push([bounds.minX, bottom + i * grid.height, bounds.maxX, bottom + i * grid.height]);
    return lines;
  });
  const offscreen = $derived.by(() => {
    if (!position) return null;
    const { width, height } = plane.view;
    const point = plane.project(position);
    if (point.x > 0 && point.x < width && point.y > 0 && point.y < height) return null;
    const pad = 16;
    return {
      x: Math.max(pad, Math.min(width - pad, point.x)),
      y: Math.max(pad, Math.min(height - pad, point.y)),
      rotation: (Math.atan2(point.y - height / 2, point.x - width / 2) * 180) / Math.PI
    };
  });

  function rect(at: Point, size: { width: number; height: number }) {
    return { x: at.x - size.width / 2, y: at.y - size.height / 2, width: size.width, height: size.height };
  }
</script>

<Group listening={false} {...Geometry.world(plane.view.scale)}>
  {#if grid}
    {#each gridLines as points, index (index)}
      <Line {points} stroke={plane.colors.fg} strokeWidth={1} strokeScaleEnabled={false} opacity={0.2} />
    {/each}
  {/if}
  {#if highlighted && footprint}
    <Rect {...rect(highlighted, footprint)} fill={plane.colors.fg} opacity={0.08} />
    <Rect
      {...rect(highlighted, footprint)}
      stroke={plane.colors.fg}
      strokeWidth={1}
      strokeScaleEnabled={false}
      dash={[3, 3]}
      opacity={0.4}
    />
  {/if}
  {#if target && frame}
    <Rect {...rect(target, frame)} {stroke} strokeWidth={1.5} strokeScaleEnabled={false} dash={[6, 4]} opacity={0.7} />
  {/if}
  {#if position}
    {#if frame}
      <Rect {...rect(position, frame)} {stroke} strokeWidth={1} strokeScaleEnabled={false} opacity={0.7} />
    {/if}
    <Group x={position.x} y={position.y} scaleX={1 / plane.view.scale} scaleY={1 / plane.view.scale}>
      <Line points={[-7, 0, 7, 0]} {stroke} strokeWidth={1.5} strokeScaleEnabled={false} />
      <Line points={[0, -7, 0, 7]} {stroke} strokeWidth={1.5} strokeScaleEnabled={false} />
    </Group>
  {/if}
</Group>

{#if offscreen}
  <Group {...Geometry.screen(plane.view)}>
    <Group
      x={offscreen.x}
      y={offscreen.y}
      rotation={offscreen.rotation}
      onpointerclick={(event) => {
        event.cancelBubble = true;
        oncenter?.();
      }}
      onpointerenter={() => plane.setCursor('pointer')}
      onpointerleave={() => plane.setCursor('grab')}
    >
      <Circle radius={11} fill={plane.colors.floating} stroke={plane.colors.lineMuted} strokeWidth={1} />
      <Line points={[-4, -5, 5, 0, -4, 5]} closed fill={plane.colors.fg} />
    </Group>
  </Group>
{/if}
