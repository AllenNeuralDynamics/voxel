<script module lang="ts">
  export interface RoutingSplit {
    id: string;
    label: string;
    axis: 'x' | 'y';
    threshold: number;
    lower: string;
    upper: string;
  }

  /** An interaction intent, not a persistence or hardware command. */
  export interface ThresholdEdit {
    id: string;
    threshold: number;
    phase: 'start' | 'move' | 'end';
  }
</script>

<script lang="ts">
  import type Konva from 'konva';
  import { onDestroy, onMount, type Snippet, untrack } from 'svelte';
  import { Group, Line, Text } from 'svelte-konva';

  import { getStageContext, type MenuSelection } from './context.svelte';
  import { type Point, screenRect, screenTransform } from './geometry';

  let {
    rule,
    visible = $bindable(true),
    disabled = false,
    index = 0,
    color = '#d4d4d8',
    haloColor = '#18181b',
    formatDistance = (value) => `${Number(value.toFixed(1))} µm`,
    resolveThreshold = (value) => value,
    onedit,
    menu
  }: {
    rule: RoutingSplit;
    visible?: boolean;
    disabled?: boolean;
    index?: number;
    color?: string;
    haloColor?: string;
    formatDistance?: (value: number) => string;
    /** Resolve a drag position in world units before moving the line. */
    resolveThreshold?: (value: number) => number;
    onedit?: (edit: ThresholdEdit) => void;
    menu?: Snippet<[MenuSelection]>;
  } = $props();

  const context = getStageContext();
  const bounds = $derived(context.bounds);
  const view = $derived(context.view);
  const orientation = $derived(context.orientation);
  const visibleBounds = $derived(context.visibleBounds ?? bounds);
  const canStartDrag = $derived(visible && !disabled && context.interactionEnabled && !!onedit);
  let line = $state<Line>();
  let thresholdText = $state<Text>();
  let value = $state<number | null>(null);
  let dragAxis: 'x' | 'y' = 'x';
  let hovered = $state(false);
  const threshold = $derived(value ?? rule.threshold);
  const vertical = $derived(rule.axis === 'x');
  const frame = $derived(screenRect(visibleBounds, view, orientation));
  const fullFrame = $derived(screenRect(bounds, view, orientation));
  const point = $derived(context.project({ x: threshold, y: threshold }));
  const thresholdLabel = $derived(formatDistance(threshold));
  const thresholdWidth = $derived(thresholdText?.node.measureSize(thresholdLabel).width ?? 0);
  const flipThreshold = $derived(vertical && point.x + thresholdWidth + 12 > frame.x + frame.width);
  const splitVisible = $derived(
    vertical
      ? threshold >= visibleBounds.minX && threshold <= visibleBounds.maxX
      : threshold >= visibleBounds.minY && threshold <= visibleBounds.maxY
  );
  const labels = $derived.by(() => {
    const min = vertical ? visibleBounds.minX : visibleBounds.minY;
    const max = vertical ? visibleBounds.maxX : visibleBounds.maxY;
    return [
      { side: 'lower', text: rule.lower, start: min, end: Math.min(threshold, max) },
      { side: 'upper', text: rule.upper, start: Math.max(threshold, min), end: max }
    ]
      .filter((region) => region.end > region.start)
      .map((region) => ({
        side: region.side,
        text: region.text,
        rect: screenRect(
          vertical
            ? { ...visibleBounds, minX: region.start, maxX: region.end }
            : { ...visibleBounds, minY: region.start, maxY: region.end },
          view,
          orientation
        )
      }));
  });

  function cursor(active: boolean) {
    hovered = active;
    const container = line?.node.getStage()?.container();
    if (container)
      container.style.cursor =
        value !== null || (active && canStartDrag) ? (vertical ? 'ew-resize' : 'ns-resize') : 'grab';
  }

  function emit(phase: ThresholdEdit['phase']) {
    onedit?.({ id: rule.id, threshold, phase });
  }

  function constrain(position: Point): Point {
    const world = context.unproject(position);
    const resolved = resolveThreshold(world[rule.axis]);
    const screen = context.project({ x: resolved, y: resolved });
    return vertical ? { x: screen.x, y: 0 } : { x: 0, y: screen.y };
  }

  function move(event: Konva.KonvaEventObject<MouseEvent | PointerEvent | TouchEvent>) {
    if (value === null) return;
    const position = context.unproject(event.target.getAbsolutePosition());
    value = resolveThreshold(position[dragAxis]);
    emit('move');
  }

  function finish() {
    if (value === null) return;
    const finalValue = value;
    value = null;
    if (line?.node.isDragging()) line.node.stopDrag();
    cursor(false);
    onedit?.({ id: rule.id, threshold: finalValue, phase: 'end' });
  }

  $effect(() => {
    if (!visible || disabled || !onedit || rule.axis !== dragAxis) untrack(finish);
  });
  onMount(() =>
    context.register({
      id: 'routing:' + rule.id,
      menuOrder: 2,
      get label() {
        return 'Routing · ' + rule.label;
      },
      get visible() {
        return visible;
      },
      setVisible: (next) => {
        visible = next;
      },
      menu: (selection) => ('hits' in selection && line && selection.hits.includes(line.node) ? menu : undefined)
    })
  );
  onDestroy(finish);
</script>

<svelte:window onblur={finish} onpointercancel={finish} />

<Group {...screenTransform(view)} {visible}>
  {#if context.visibleBounds && (splitVisible || value !== null)}
    <Line
      bind:this={line}
      id={`routing:${rule.id}`}
      x={vertical ? point.x : 0}
      y={vertical ? 0 : point.y}
      points={vertical
        ? [0, fullFrame.y, 0, fullFrame.y + fullFrame.height]
        : [fullFrame.x, 0, fullFrame.x + fullFrame.width, 0]}
      stroke={color}
      strokeWidth={(hovered && canStartDrag) || value !== null ? 2 : 1}
      opacity={0.8}
      dash={[5, 4]}
      hitStrokeWidth={12}
      draggable={value !== null || canStartDrag}
      dragDistance={4}
      dragBoundFunc={constrain}
      onmouseenter={() => cursor(true)}
      onmouseleave={() => cursor(false)}
      ondragstart={() => {
        dragAxis = rule.axis;
        value = rule.threshold;
        cursor(hovered);
        emit('start');
      }}
      ondragmove={move}
      ondragend={(event) => {
        if (value === null) return;
        move(event);
        finish();
      }}
    />
    <Text
      bind:this={thresholdText}
      x={vertical ? point.x + (flipThreshold ? -6 : 6) : frame.x + frame.width - 8}
      y={vertical
        ? Math.max(frame.y + 14, frame.y + frame.height - 14 - index * 18)
        : point.y + (point.y - 16 < frame.y ? 10 : -10)}
      offsetX={!vertical || flipThreshold ? thresholdWidth : 0}
      offsetY={7}
      height={14}
      verticalAlign="middle"
      wrap="none"
      text={thresholdLabel}
      fontSize={11}
      fontFamily="sans-serif"
      fill={color}
      stroke={haloColor}
      strokeWidth={3}
      lineJoin="round"
      fillAfterStrokeEnabled
      opacity={0.65}
      listening={false}
    />
  {/if}
  {#each labels as label (label.side)}
    {@const length = (vertical ? label.rect.width : label.rect.height) - 16}
    {@const inset = 14 + index * 20}
    {#if context.visibleBounds && length >= 32 && inset + 8 <= (vertical ? label.rect.height : label.rect.width)}
      <Text
        x={vertical ? label.rect.x + label.rect.width / 2 : label.rect.x + inset}
        y={vertical ? label.rect.y + inset : label.rect.y + label.rect.height / 2}
        offsetX={length / 2}
        offsetY={7}
        width={length}
        height={14}
        verticalAlign="middle"
        rotation={vertical ? 0 : -90}
        text={label.text}
        wrap="none"
        ellipsis
        align={vertical ? (label.rect.x < point.x ? 'right' : 'left') : label.rect.y < point.y ? 'left' : 'right'}
        fontSize={11}
        fontFamily="sans-serif"
        fill={color}
        stroke={haloColor}
        strokeWidth={3}
        lineJoin="round"
        fillAfterStrokeEnabled
        opacity={0.65}
        listening={false}
      />
    {/if}
  {/each}
</Group>
