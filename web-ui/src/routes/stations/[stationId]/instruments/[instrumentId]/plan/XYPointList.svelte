<script lang="ts">
  import { Crosshair, GripVertical, TrashCanOutline } from '$lib/icons';
  import { Button } from '$lib/kit';
  import * as Sortable from '$lib/kit/sortable';
  import type { EditContext, Point2D } from '$lib/model';
  import { prefs } from '$lib/prefs';
  import { Input as NumericInput } from '$lib/prop/numeric';
  import { getSpatialUnit } from '$lib/spatial-units';
  import { cn } from '$lib/utils';

  interface Props {
    points: readonly Point2D[];
    current?: Readonly<Point2D> | null;
    minimum?: number;
    disabled?: boolean;
    onchange: (points: Point2D[], context?: EditContext) => void;
    class?: string;
  }

  let { points, current = null, minimum = 1, disabled = false, onchange, class: className = '' }: Props = $props();

  const unit = $derived(getSpatialUnit(prefs.spatialUnit.get()));
  const sortablePoints = $derived(points.map((point) => ({ key: `${point.x}\0${point.y}`, point })));

  function reorder(items: { key: string; point: Point2D }[]): void {
    onchange(items.map(({ point }) => point));
  }

  function replace(index: number, point: Point2D, context?: EditContext): void {
    onchange(
      points.map((currentPoint, pointIndex) => (pointIndex === index ? point : currentPoint)),
      context
    );
  }

  function update(index: number, axis: keyof Point2D, value: number, context: EditContext): void {
    const point = points[index];
    if (!point || Object.is(point[axis], value)) return;
    replace(index, { ...point, [axis]: value }, context);
  }

  function canUseCurrent(index: number): boolean {
    if (!current) return false;
    const point = points[index];
    if (point?.x === current.x && point.y === current.y) return false;
    return !points.some(
      (candidate, pointIndex) => pointIndex !== index && candidate.x === current.x && candidate.y === current.y
    );
  }

  function useCurrent(index: number): void {
    if (current && canUseCurrent(index)) replace(index, { ...current });
  }

  function remove(index: number): void {
    if (points.length <= minimum) return;
    onchange(points.filter((_, pointIndex) => pointIndex !== index));
  }
</script>

{#snippet coordinate(value: number, label: string, onchange: (value: number, context: EditContext) => void)}
  <div class="flex min-w-0 items-center">
    <NumericInput
      model={{
        value,
        step: unit.step * unit.scale,
        bigStep: unit.bigStep * unit.scale,
        disabled,
        onChange: onchange
      }}
      displayScale={unit.scale}
      decimals={unit.decimals}
      numCharacters={8}
      align="right"
      {disabled}
      aria-label={label}
      class="min-w-0 flex-1 basis-0 px-1 leading-none"
    />
    <span class="pointer-events-none shrink-0 pr-1.5 pl-0.5 font-mono text-fg-muted">{unit.label}</span>
  </div>
{/snippet}

{#snippet pointRow(item: { key: string; point: Point2D }, index: number)}
  <Sortable.Item
    {item}
    class="focus-within:border-focused grid h-ui-xs grid-cols-[var(--spacing-ui-xs)_minmax(0,16rem)_minmax(0,1fr)_var(--spacing-ui-xs)_var(--spacing-ui-xs)] overflow-hidden rounded border border-control-line bg-element-bg transition-colors hover:bg-element-hover"
  >
    <Sortable.Handle
      {item}
      {disabled}
      class="flex size-ui-xs shrink-0 cursor-grab touch-none items-center justify-center text-fg-muted active:cursor-grabbing"
    >
      <GripVertical class="size-3.5" />
    </Sortable.Handle>

    <div class="grid min-w-0 cursor-auto grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center">
      {@render coordinate(item.point.x, `Point ${index + 1} X`, (value, context) => update(index, 'x', value, context))}
      <span class="px-0.5 text-fg-muted select-none">,</span>
      {@render coordinate(item.point.y, `Point ${index + 1} Y`, (value, context) => update(index, 'y', value, context))}
    </div>

    <span aria-hidden="true"></span>

    <Button
      variant="ghost"
      size="icon-xs"
      class="h-full rounded-none border-y-0 border-r-0 border-l border-control-line text-fg-muted focus-visible:ring-offset-0 focus-visible:ring-inset"
      disabled={disabled || !canUseCurrent(index)}
      aria-label={`Use current stage position for point ${index + 1}`}
      title="Use current stage position"
      onclick={() => useCurrent(index)}
    >
      <Crosshair class="size-3.5" />
    </Button>
    <Button
      variant="ghost"
      size="icon-xs"
      class="h-full rounded-none border-y-0 border-r-0 border-l border-control-line text-fg-muted hover:text-danger focus-visible:ring-offset-0 focus-visible:ring-inset"
      disabled={disabled || points.length <= minimum}
      aria-label={`Delete point ${index + 1}`}
      title={`Delete point ${index + 1}`}
      onclick={() => remove(index)}
    >
      <TrashCanOutline class="size-3.5" />
    </Button>
  </Sortable.Item>
{/snippet}

<Sortable.Root
  items={sortablePoints}
  key={(item) => item.key}
  onReorder={reorder}
  item={pointRow}
  layout="vertical"
  flipDuration={120}
  class={cn('space-y-2 overflow-y-auto', className)}
/>
