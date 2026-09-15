<script lang="ts">
  import { onMount, tick, untrack } from 'svelte';
  import { Group, Line, Rect } from 'svelte-konva';

  import { getStageContext } from './context.svelte';
  import { type Bounds, type Point, screenTransform, worldTransform } from './geometry';

  let {
    position,
    fov,
    target = null,
    constrain = (point: Point) => point,
    color
  }: {
    position: Point | null;
    fov: { width: number; height: number } | null;
    target?: Point | null;
    constrain?: (point: Point) => Point;
    color?: string;
  } = $props();

  const context = getStageContext();
  let group = $state<Group>();
  let markerColor = $state('#e254d4');
  const stroke = $derived(color ?? markerColor);
  let grid = $state<{ origin: Point; width: number; height: number } | null>(null);

  $effect(() => {
    if (!context.altHeld && !context.menuSelection) grid = null;
    else if (context.altHeld && !context.menuSelection && !grid) {
      grid = untrack(() =>
        position && fov && fov.width > 0 && fov.height > 0 ? { origin: { ...position }, ...fov } : null
      );
    }
  });

  function contains(bounds: Bounds, point: Point) {
    return point.x >= bounds.minX && point.x <= bounds.maxX && point.y >= bounds.minY && point.y <= bounds.maxY;
  }

  export function destination(point: Point): Point | undefined {
    if (!grid || !contains(context.bounds, point)) return;
    return constrain({
      x: grid.origin.x + Math.round((point.x - grid.origin.x) / grid.width) * grid.width,
      y: grid.origin.y + Math.round((point.y - grid.origin.y) / grid.height) * grid.height
    });
  }

  const highlighted = $derived.by(() => {
    const selection = context.menuSelection;
    if (selection) return 'point' in selection ? selection.destination : undefined;
    if (!grid) return;
    const point = context.cursor;
    if (!point || context.selecting || (context.marquee && contains(context.marquee, point))) return;
    return destination(point);
  });
  const footprint = $derived(grid ?? fov);
  const offscreen = $derived.by(() => {
    if (!position || !fov) return null;
    const { width, height, scale } = context.view;
    const point = context.project(position);
    const halfWidth = (fov.width * scale) / 2;
    const halfHeight = (fov.height * scale) / 2;
    if (
      point.x + halfWidth > 0 &&
      point.x - halfWidth < width &&
      point.y + halfHeight > 0 &&
      point.y - halfHeight < height
    )
      return null;
    const padX = Math.min(16, width / 2);
    const padY = Math.min(16, height / 2);
    return {
      x: Math.max(padX, Math.min(width - padX, point.x)),
      y: Math.max(padY, Math.min(height - padY, point.y)),
      rotation: (Math.atan2(point.y - height / 2, point.x - width / 2) * 180) / Math.PI
    };
  });

  const gridLines = $derived.by(() => {
    const bounds = context.visibleBounds;
    if (!grid || !bounds) return [];
    const lines: number[][] = [];
    const left = grid.origin.x - grid.width / 2;
    const bottom = grid.origin.y - grid.height / 2;
    for (
      let i = Math.ceil((bounds.minX - left) / grid.width);
      i <= Math.floor((bounds.maxX - left) / grid.width);
      i++
    ) {
      const x = left + i * grid.width;
      lines.push([x, bounds.minY, x, bounds.maxY]);
    }
    for (
      let i = Math.ceil((bounds.minY - bottom) / grid.height);
      i <= Math.floor((bounds.maxY - bottom) / grid.height);
      i++
    ) {
      const y = bottom + i * grid.height;
      lines.push([bounds.minX, y, bounds.maxX, y]);
    }
    return lines;
  });

  onMount(async () => {
    await tick();
    const container = group?.node.getStage()?.container();
    if (container) markerColor = getComputedStyle(container).getPropertyValue('--stage-marker').trim() || markerColor;
  });
</script>

<Group bind:this={group} listening={false} {...worldTransform(context.view.scale, context.orientation)}>
  {#if grid || (highlighted && footprint)}
    <Group
      clipX={context.bounds.minX}
      clipY={context.bounds.minY}
      clipWidth={context.bounds.maxX - context.bounds.minX}
      clipHeight={context.bounds.maxY - context.bounds.minY}
    >
      {#each gridLines as points, index (index)}
        <Line {points} {stroke} strokeWidth={1} strokeScaleEnabled={false} opacity={0.2} />
      {/each}
      {#if highlighted && footprint}
        {@const rect = {
          x: highlighted.x - footprint.width / 2,
          y: highlighted.y - footprint.height / 2,
          width: footprint.width,
          height: footprint.height
        }}
        <Rect {...rect} fill={stroke} opacity={0.08} />
        <Rect {...rect} {stroke} strokeWidth={1} strokeScaleEnabled={false} dash={[3, 3]} opacity={0.4} />
      {/if}
    </Group>
  {/if}
  {#if target && fov}
    <Rect
      x={target.x - fov.width / 2}
      y={target.y - fov.height / 2}
      width={fov.width}
      height={fov.height}
      {stroke}
      strokeWidth={1.5}
      strokeScaleEnabled={false}
      dash={[6, 4]}
      opacity={0.7}
    />
  {/if}
  {#if position && fov}
    <Rect
      x={position.x - fov.width / 2}
      y={position.y - fov.height / 2}
      width={fov.width}
      height={fov.height}
      {stroke}
      strokeWidth={1}
      strokeScaleEnabled={false}
      opacity={0.7}
    />
    <Group x={position.x} y={position.y} scaleX={1 / context.view.scale} scaleY={1 / context.view.scale}>
      <Line points={[-6, 0, 6, 0]} {stroke} strokeWidth={1.5} strokeScaleEnabled={false} />
      <Line points={[0, -6, 0, 6]} {stroke} strokeWidth={1.5} strokeScaleEnabled={false} />
    </Group>
  {/if}
</Group>

{#if offscreen}
  <Group {...screenTransform(context.view)} listening={false}>
    <Line {...offscreen} points={[7, 0, -5, -6, -5, 6]} closed fill={stroke} opacity={0.35} />
  </Group>
{/if}
