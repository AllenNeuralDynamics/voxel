<script module lang="ts">
  import type { Point2D } from '$lib/model';

  export interface TaskPointEdit {
    task: string;
    index: number;
    point: Point2D;
    phase: 'start' | 'move' | 'end';
  }
</script>

<script lang="ts">
  import type Konva from 'konva';
  import { untrack } from 'svelte';
  import { Circle, Group, Label, Line, Rect, Shape, Tag, Text } from 'svelte-konva';

  import type { AcquisitionTask, FootprintBounds, PlannedVolume } from '$lib/model';

  import { getStageContext } from './context.svelte';
  import { type Bounds, intersect, type Point, screenTransform, worldTransform } from './geometry';

  let {
    plan,
    volumes,
    profileFovs,
    taskVisibility = $bindable({}),
    pathVisible = $bindable(true),
    disabled = false,
    color = '#d4d4d8',
    fill,
    haloColor = '#18181b',
    onactivate,
    onpointedit
  }: {
    plan: readonly AcquisitionTask[];
    volumes: readonly PlannedVolume[];
    profileFovs: Readonly<Record<string, Readonly<Record<string, FootprintBounds>>>>;
    taskVisibility?: Record<string, boolean>;
    pathVisible?: boolean;
    disabled?: boolean;
    color?: string;
    fill?: (volume: PlannedVolume) => string | undefined;
    haloColor?: string;
    onactivate?: (point: Point) => void;
    onpointedit?: (edit: TaskPointEdit) => void;
  } = $props();

  interface VolumeTile {
    bounds: Bounds;
    color: string | undefined;
    key: string;
    order: number;
    point: Point;
    profile: string;
    task: string;
    taskOrder: number | undefined;
  }

  const context = getStageContext();
  const taskOrder = $derived(new Map(plan.map((task, index) => [task.id, index + 1])));
  const taskVisible = (task: string) => taskVisibility[task] ?? true;
  const tiles = $derived.by(() => {
    const result: VolumeTile[] = [];
    for (const [index, volume] of volumes.entries()) {
      const seen: string[] = [];
      for (const footprint of Object.values(profileFovs[volume.profile] ?? {})) {
        const bounds = absoluteBounds(volume, footprint);
        if (!valid(bounds)) continue;
        const key = boundsKey(bounds);
        if (seen.includes(key)) continue;
        seen.push(key);
        result.push({
          bounds,
          color: fill?.(volume),
          key: `${index + 1}:${key}`,
          order: index + 1,
          point: { x: volume.x, y: volume.y },
          profile: volume.profile,
          task: volume.task,
          taskOrder: taskOrder.get(volume.task)
        });
      }
    }
    return result;
  });
  const drawn = $derived(
    context.visibleBounds
      ? tiles.filter((tile) => taskVisible(tile.task) && intersect(tile.bounds, context.visibleBounds!))
      : []
  );
  const path = $derived.by(() => {
    const points: (Point & { task: string })[] = [];
    for (const { task, x, y } of volumes) {
      const previous = points.at(-1);
      if (!previous || previous.task !== task || previous.x !== x || previous.y !== y) points.push({ task, x, y });
    }
    return points;
  });
  const pathSegments = $derived(
    path.slice(1).flatMap((end, index) => {
      const start = path[index];
      return taskVisible(start.task) && taskVisible(end.task) ? [{ start, end }] : [];
    })
  );
  const traversalScene = $derived.by(() => {
    const segments = pathSegments;
    const stroke = color;
    const pixel = 1 / context.view.scale;
    return (drawing: Konva.Context) => {
      if (!segments.length) return;

      drawing.setAttr('strokeStyle', stroke);
      drawing.setAttr('lineWidth', 1.25 * pixel);
      drawing.setAttr('globalAlpha', 0.2);
      drawing.beginPath();
      for (const { start, end } of segments) {
        drawing.moveTo(start.x, start.y);
        drawing.lineTo(end.x, end.y);
      }
      drawing.stroke();

      drawing.setAttr('globalAlpha', 0.32);
      drawing.beginPath();
      for (const { start, end } of segments) {
        const dx = end.x - start.x;
        const dy = end.y - start.y;
        const length = Math.hypot(dx, dy);
        if (length < 24 * pixel) continue;
        const x = (start.x + end.x) / 2;
        const y = (start.y + end.y) / 2;
        const cos = dx / length;
        const sin = dy / length;
        const arm = 4 * pixel;
        drawing.moveTo(x - arm * cos + arm * sin, y - arm * sin - arm * cos);
        drawing.lineTo(x, y);
        drawing.lineTo(x - arm * cos - arm * sin, y - arm * sin + arm * cos);
      }
      drawing.stroke();
    };
  });

  const hovered = $derived.by(() => {
    const cursor = context.cursor;
    if (!context.interactionEnabled || !cursor) return null;
    let result: VolumeTile | null = null;
    for (const tile of drawn) {
      const { bounds } = tile;
      if (
        cursor.x >= bounds.minX &&
        cursor.x <= bounds.maxX &&
        cursor.y >= bounds.minY &&
        cursor.y <= bounds.maxY &&
        (!result || area(bounds) < area(result.bounds))
      )
        result = tile;
    }
    return result;
  });
  const hoverKey = $derived(hovered ? hovered.key : '');
  let ready = $state(false);
  let hoveredPoint = $state<string | null>(null);
  let editing = $state<{ task: string; index: number; point: Point } | null>(null);

  $effect(() => {
    const key = hoverKey;
    ready = false;
    if (!key) return;
    const timer = setTimeout(() => (ready = true), 1000);
    return () => clearTimeout(timer);
  });

  const tooltip = $derived.by(() => {
    if (!ready || !hovered || !context.cursor) return null;
    const text = [
      `Volume ${hovered.order}`,
      hovered.taskOrder === undefined ? undefined : `Task ${hovered.taskOrder}`,
      hovered.profile
    ]
      .filter((line) => line !== undefined)
      .join('\n');
    const point = context.project(context.cursor);
    const width = Math.max(...text.split('\n').map((line) => line.length)) * 8 + 12;
    const height = text.split('\n').length * 16 + 12;
    return {
      point: {
        x: Math.max(4, Math.min(point.x + 12, context.view.width - width - 4)),
        y: Math.max(4, Math.min(point.y + 12, context.view.height - height - 4))
      },
      text,
      width,
      height
    };
  });

  export function destinations(hits: readonly Konva.Shape[]) {
    const orders = new Set(
      hits.flatMap((hit) =>
        hit
          .name()
          .split(/\s+/)
          .filter((name) => name.startsWith('volume:'))
          .map((name) => Number(name.slice('volume:'.length)))
      )
    );
    return volumes.flatMap((volume, index) =>
      orders.has(index + 1)
        ? [
            {
              order: index + 1,
              task: volume.task,
              taskOrder: taskOrder.get(volume.task),
              profile: volume.profile,
              point: { x: volume.x, y: volume.y }
            }
          ]
        : []
    );
  }

  export function extent(): Bounds | null {
    let result: Bounds | null = null;
    for (const { bounds, task } of tiles) {
      if (!taskVisible(task)) continue;
      result = result
        ? {
            minX: Math.min(result.minX, bounds.minX),
            minY: Math.min(result.minY, bounds.minY),
            maxX: Math.max(result.maxX, bounds.maxX),
            maxY: Math.max(result.maxY, bounds.maxY)
          }
        : bounds;
    }
    return result;
  }

  function absoluteBounds(volume: PlannedVolume, footprint: FootprintBounds): Bounds {
    return {
      minX: volume.x + footprint.min_x,
      minY: volume.y + footprint.min_y,
      maxX: volume.x + footprint.max_x,
      maxY: volume.y + footprint.max_y
    };
  }

  function valid(bounds: Bounds) {
    return Object.values(bounds).every(Number.isFinite) && bounds.maxX > bounds.minX && bounds.maxY > bounds.minY;
  }

  function boundsKey(bounds: Bounds) {
    return `${bounds.minX}:${bounds.minY}:${bounds.maxX}:${bounds.maxY}`;
  }

  function area(bounds: Bounds) {
    return (bounds.maxX - bounds.minX) * (bounds.maxY - bounds.minY);
  }

  function taskPoints(task: AcquisitionTask): Point[] {
    return task.layout.points.map((point, index) =>
      editing?.task === task.id && editing.index === index ? editing.point : point
    );
  }

  function edit(task: AcquisitionTask, index: number, point: Point, phase: TaskPointEdit['phase']) {
    onpointedit?.({ task: task.id, index, point, phase });
  }

  function movePoint(
    task: AcquisitionTask,
    index: number,
    event: Konva.KonvaEventObject<MouseEvent | PointerEvent | TouchEvent>
  ) {
    const point = context.unproject(event.target.getAbsolutePosition());
    editing = { task: task.id, index, point };
    edit(task, index, point, 'move');
  }

  function finishPoint(
    task: AcquisitionTask,
    index: number,
    event: Konva.KonvaEventObject<MouseEvent | PointerEvent | TouchEvent>
  ) {
    const point = context.unproject(event.target.getAbsolutePosition());
    editing = null;
    event.target.getStage()!.container().style.cursor = 'grab';
    edit(task, index, point, 'end');
  }

  $effect(() => {
    const tasks = plan.map(({ id }, index) => ({ id, index }));
    const registrations = untrack(() => [
      ...tasks.map((task) =>
        context.register({
          id: `task:${task.id}`,
          label: `Task ${task.index + 1}`,
          menuOrder: 1 + task.index / tasks.length,
          get visible() {
            return taskVisible(task.id);
          },
          setVisible: (visible) => {
            taskVisibility = { ...taskVisibility, [task.id]: visible };
          }
        })
      ),
      context.register({
        id: 'acquisition-path',
        label: 'Acquisition path',
        menuOrder: 2,
        get visible() {
          return pathVisible;
        },
        setVisible: (visible) => {
          pathVisible = visible;
        }
      })
    ]);
    return () => untrack(() => registrations.forEach((unregister) => unregister()));
  });
  function transparent(color: string, opacity: number) {
    const match = /^#([\da-f]{2})([\da-f]{2})([\da-f]{2})$/i.exec(color);
    if (!match) return color;
    return `rgba(${parseInt(match[1], 16)}, ${parseInt(match[2], 16)}, ${parseInt(match[3], 16)}, ${opacity})`;
  }
</script>

<Group {...worldTransform(context.view.scale, context.orientation)}>
  {#each drawn as tile (tile.key)}
    <Rect
      staticConfig
      x={tile.bounds.minX}
      y={tile.bounds.minY}
      width={tile.bounds.maxX - tile.bounds.minX}
      height={tile.bounds.maxY - tile.bounds.minY}
      name={`volume:${tile.order}`}
      fill={transparent(tile.color ?? color, tile.color ? 0.12 : 0.02)}
      stroke={transparent(tile.color ?? color, 0.25)}
      strokeWidth={1}
      strokeScaleEnabled={false}
      perfectDrawEnabled={false}
      shadowForStrokeEnabled={false}
      onpointerdblclick={() => {
        if (context.interactionEnabled) onactivate?.(tile.point);
      }}
    />
  {/each}
  {#each plan as task (task.id)}
    {#if taskVisible(task.id)}
      {@const points = taskPoints(task)}
      {#if task.layout.type === 'area' && points.length > 1}
        <Line
          points={points.flatMap(({ x, y }) => [x, y])}
          closed={points.length > 2}
          stroke={transparent(color, 0.45)}
          strokeWidth={1}
          strokeScaleEnabled={false}
          listening={false}
        />
      {/if}
    {/if}
  {/each}
  {#if pathVisible && pathSegments.length}
    <Shape staticConfig sceneFunc={traversalScene} listening={false} perfectDrawEnabled={false} />
  {/if}
</Group>
<Group {...screenTransform(context.view)}>
  {#each plan as task (task.id)}
    {#if taskVisible(task.id)}
      {#each taskPoints(task) as point, index (`${task.id}:${index}`)}
        {@const screen = context.project(point)}
        {@const pointKey = `${task.id}:${index}`}
        {@const active = hoveredPoint === pointKey || (editing?.task === task.id && editing.index === index)}
        <Circle
          x={Math.round(screen.x)}
          y={Math.round(screen.y)}
          radius={3}
          fill={active ? color : transparent(color, 0.45)}
          stroke="transparent"
          strokeWidth={1}
          hitStrokeWidth={4}
          perfectDrawEnabled={false}
          draggable={!disabled && !!onpointedit && context.interactionEnabled}
          dragDistance={4}
          onmouseenter={(event) => {
            hoveredPoint = pointKey;
            if (!disabled && onpointedit && context.interactionEnabled)
              event.target.getStage()!.container().style.cursor = 'move';
          }}
          onmouseleave={(event) => {
            if (hoveredPoint === pointKey) hoveredPoint = null;
            if (!editing) event.target.getStage()!.container().style.cursor = 'grab';
          }}
          ondragstart={(event) => {
            editing = { task: task.id, index, point };
            event.target.getStage()!.container().style.cursor = 'move';
            edit(task, index, point, 'start');
          }}
          ondragmove={(event) => movePoint(task, index, event)}
          ondragend={(event) => finishPoint(task, index, event)}
        />
      {/each}
    {/if}
  {/each}
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
</Group>
