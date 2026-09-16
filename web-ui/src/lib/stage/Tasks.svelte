<script lang="ts">
  import type Konva from 'konva';
  import { onMount } from 'svelte';
  import { Group, Label, Rect, Shape, Tag, Text } from 'svelte-konva';

  import { Check } from '$lib/icons';
  import { ContextMenu } from '$lib/kit';
  import type { TaskTile } from '$lib/model';

  import { getStageContext, type MenuSelection } from './context.svelte';
  import { intersect, type Point, screenRect, screenTransform } from './geometry';

  let {
    tiles,
    selected,
    visible = $bindable(true),
    color = '#d4d4d8',
    fill,
    haloColor = '#18181b',
    onselect,
    onactivate
  }: {
    tiles: readonly TaskTile[];
    selected: ReadonlySet<string>;
    visible?: boolean;
    color?: string;
    fill?: (tile: TaskTile) => string | undefined;
    haloColor?: string;
    onselect: (ids: string[], toggle?: boolean) => void;
    onactivate?: (point: Point) => void;
  } = $props();

  const context = getStageContext();
  const items = $derived(
    tiles.flatMap((tile, index) =>
      [tile.x, tile.y, tile.w, tile.h].every(Number.isFinite) && tile.w > 0 && tile.h > 0
        ? [
            {
              id: tile.task_id,
              order: index + 1,
              fill: fill?.(tile),
              bounds: {
                minX: tile.x - tile.w / 2,
                maxX: tile.x + tile.w / 2,
                minY: tile.y - tile.h / 2,
                maxY: tile.y + tile.h / 2
              }
            }
          ]
        : []
    )
  );
  const drawn = $derived(
    context.visibleBounds ? items.filter((item) => intersect(item.bounds, context.visibleBounds!)) : []
  );
  const path = $derived(
    items.map(({ bounds }) =>
      context.project({ x: (bounds.minX + bounds.maxX) / 2, y: (bounds.minY + bounds.maxY) / 2 })
    )
  );
  const traversalScene = $derived.by(() => {
    const points = path;
    const stroke = color;
    return (drawing: Konva.Context) => {
      if (points.length < 2) return;

      drawing.setAttr('strokeStyle', stroke);
      drawing.setAttr('lineWidth', 1.5);
      drawing.setAttr('globalAlpha', 0.35);
      drawing.beginPath();
      drawing.moveTo(points[0].x, points[0].y);
      for (const point of points.slice(1)) drawing.lineTo(point.x, point.y);
      drawing.stroke();

      drawing.setAttr('globalAlpha', 0.6);
      drawing.beginPath();
      for (let index = 0; index < points.length - 1; index++) {
        const start = points[index];
        const end = points[index + 1];
        const dx = end.x - start.x;
        const dy = end.y - start.y;
        const length = Math.hypot(dx, dy);
        if (length < 24) continue;
        const x = (start.x + end.x) / 2;
        const y = (start.y + end.y) / 2;
        const cos = dx / length;
        const sin = dy / length;
        drawing.moveTo(x - 4 * cos + 4 * sin, y - 4 * sin - 4 * cos);
        drawing.lineTo(x, y);
        drawing.lineTo(x - 4 * cos - 4 * sin, y - 4 * sin + 4 * cos);
      }
      drawing.stroke();
    };
  });
  const hovered = $derived.by(() => {
    const cursor = context.cursor;
    if (!visible || !context.interactionEnabled || !cursor) return [];
    return items.filter(
      ({ bounds }) =>
        cursor.x >= bounds.minX && cursor.x <= bounds.maxX && cursor.y >= bounds.minY && cursor.y <= bounds.maxY
    );
  });
  const hoverKey = $derived(hovered.length ? JSON.stringify(hovered.map((item) => item.id)) : '');
  let ready = $state(false);

  $effect(() => {
    const key = hoverKey;
    ready = false;
    if (!key) return;
    const timer = setTimeout(() => (ready = true), 1000);
    return () => clearTimeout(timer);
  });

  const tooltip = $derived.by(() => {
    if (!ready || !hovered.length || !context.cursor) return null;
    const labels = hovered.map((item) => `Task ${item.order}`);
    const point = context.project(context.cursor);
    const width = Math.max(...labels.map((label) => label.length)) * 8 + 12;
    const height = labels.length * 16 + 12;
    const position = {
      x: Math.max(4, Math.min(point.x + 12, context.view.width - width - 4)),
      y: Math.max(4, Math.min(point.y + 12, context.view.height - height - 4))
    };
    return { point: position, text: labels.join('\n'), width, height };
  });

  export function destinations(hits: readonly Konva.Shape[]) {
    return visible
      ? items
          .filter((item) => hits.some((hit) => hit.hasName(`task:${item.id}`)))
          .map((item) => ({
            order: item.order,
            point: { x: (item.bounds.minX + item.bounds.maxX) / 2, y: (item.bounds.minY + item.bounds.maxY) / 2 }
          }))
      : [];
  }

  onMount(() =>
    context.register({
      id: 'tasks',
      label: 'Tasks',
      get visible() {
        return visible;
      },
      setVisible: (next) => {
        visible = next;
      },
      menu: (selection) => ('bounds' in selection ? regionMenu : undefined)
    })
  );

  function transparent(color: string, opacity: number) {
    const match = /^#([\da-f]{2})([\da-f]{2})([\da-f]{2})$/i.exec(color);
    if (!match) return color;
    return `rgba(${parseInt(match[1], 16)}, ${parseInt(match[2], 16)}, ${parseInt(match[3], 16)}, ${opacity})`;
  }
</script>

{#snippet regionMenu(selection: MenuSelection)}
  {#if 'bounds' in selection}
    {@const ids = items.filter((item) => intersect(item.bounds, selection.bounds)).map((item) => item.id)}
    <ContextMenu.Item disabled={ids.length === 0} onSelect={() => onselect(ids)}>
      <Check width="14" height="14" />
      Select tasks in region ({ids.length})
    </ContextMenu.Item>
  {/if}
{/snippet}

<Group {visible} {...screenTransform(context.view)}>
  {#if visible}
    {#each drawn as item (item.id)}
      {@const rect = screenRect(item.bounds, context.view, context.orientation)}
      {@const active = selected.has(item.id)}
      <Rect
        staticConfig
        {...rect}
        name={`task:${item.id}`}
        fill={transparent(item.fill ?? color, item.fill ? (active ? 0.22 : 0.12) : active ? 0.12 : 0.02)}
        stroke={transparent(color, active ? 1 : 0.4)}
        strokeWidth={active ? 1.5 : 1}
        perfectDrawEnabled={false}
        shadowForStrokeEnabled={false}
        onpointerclick={(event) => {
          if (event.evt.button !== 0 || !context.interactionEnabled) return;
          onselect([item.id], event.evt.metaKey || event.evt.ctrlKey);
        }}
        onpointerdblclick={() => {
          if (context.interactionEnabled && context.cursor) onactivate?.(context.cursor);
        }}
      />
    {/each}
    {#if path.length > 1}
      <Shape staticConfig sceneFunc={traversalScene} listening={false} perfectDrawEnabled={false} />
    {/if}
    {#if tooltip}
      <Label x={tooltip.point.x} y={tooltip.point.y} listening={false}>
        <Tag fill={haloColor} cornerRadius={4} />
        <Text
          text={tooltip.text}
          width={tooltip.width}
          height={tooltip.height}
          padding={6}
          fontSize={12}
          lineHeight={16 / 12}
          fontFamily="sans-serif"
          fill={color}
        />
      </Label>
    {/if}
  {/if}
</Group>
