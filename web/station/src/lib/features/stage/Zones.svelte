<script lang="ts">
  import type Konva from 'konva';
  import { onMount, untrack } from 'svelte';
  import { Group, Line, Rect, Text } from 'svelte-konva';

  import { Prefs } from '$lib/core/prefs';
  import type { StageFollowRule } from '$lib/core/types';
  import type { UnitSteps } from '$lib/features/run/StageNumericField.svelte';
  import { hexWithAlpha } from '@voxel/kit/colors';
  import { reportFailure } from '@voxel/kit/failures';

  import { Plane } from './context';
  import { Geometry } from './geometry';
  import type { StagePlan } from './stage-plan.svelte';

  interface Props {
    plan: StagePlan;
    unit: UnitSteps;
    /** The lines can be dragged to move a change point. */
    editable?: boolean;
    onrule?: (device: string, rule: StageFollowRule) => Promise<void> | undefined;
  }

  let { plan, unit, editable = false, onrule }: Props = $props();

  const FONT = 'IBM Plex Sans, ui-sans-serif, system-ui, sans-serif';
  const plane = Plane.get();
  const shown = $derived(Prefs.stageZones.get());
  // A dragged change point, kept until the saved rules arrive so the line does not jump back.
  let held = $state.raw<{ key: string; at: number } | null>(null);
  let dragging = false;
  const canEdit = $derived(editable && !!onrule && plane.interactionEnabled);

  $effect(() => {
    void plan.rules;
    untrack(() => {
      if (!dragging) held = null;
    });
  });

  onMount(() =>
    plane.register({
      id: 'zones',
      label: 'Zones',
      menuOrder: 3,
      choices: [
        { value: 'off', label: 'Off' },
        { value: 'lines', label: 'Lines' },
        { value: 'areas', label: 'Lines and areas' }
      ],
      get value() {
        return shown;
      },
      setValue: (value) => Prefs.stageZones.set(value as typeof shown)
    })
  );

  const travel = $derived(plane.bounds);
  const seen = $derived(Geometry.intersect(plane.visibleBounds ?? travel, travel));
  const frame = $derived(seen ? Geometry.screenRect(seen, plane.view) : null);
  const areas = $derived(
    plan.zones.flatMap((zone) => {
      const bounds = Geometry.intersect(zone.bounds, travel);
      return bounds ? [{ index: zone.index, rect: Geometry.screenRect(bounds, plane.view) }] : [];
    })
  );
  const lines = $derived.by(() => {
    if (!seen) return [];
    const { h } = plan.axes;
    const count = { across: 0, up: 0 };
    return Object.entries(plan.rules).flatMap(([device, rule]) =>
      rule.at.map((saved, index) => {
        const key = `${device}:${index}`;
        const at = held?.key === key ? held.at : saved;
        const across = rule.axis === h;
        const stack = across ? count.across++ : count.up++;
        const low = across ? seen.minX : seen.minY;
        const high = across ? seen.maxX : seen.maxY;
        const band = across
          ? { ...travel, minX: at - rule.margin, maxX: at + rule.margin }
          : { ...travel, minY: at - rule.margin, maxY: at + rule.margin };
        return {
          key,
          device,
          rule,
          index,
          saved,
          // A change point stays inside the travel and between its neighbors.
          range: [
            Math.max(across ? travel.minX : travel.minY, (rule.at[index - 1] ?? -Infinity) + 1),
            Math.min(across ? travel.maxX : travel.maxY, (rule.at[index + 1] ?? Infinity) - 1)
          ] as [number, number],
          across,
          stack,
          at: plane.project({ x: at, y: at }),
          inside: at >= low && at <= high,
          value: `${(at / unit.scale).toFixed(unit.decimals)} ${unit.label}`,
          band: Geometry.screenRect(band, plane.view),
          names: [rule.order[index], rule.order[index + 1]].map((name) => name.charAt(0).toUpperCase() + name.slice(1))
        };
      })
    );
  });

  type ZoneLine = (typeof lines)[number];
  type DragEvent = Konva.KonvaEventObject<MouseEvent | PointerEvent | TouchEvent>;

  function drag(line: ZoneLine, event: DragEvent) {
    const node = event.target;
    const point = plane.unproject({ x: node.x(), y: node.y() });
    const at = Math.round(Math.max(line.range[0], Math.min(line.range[1], line.across ? point.x : point.y)));
    const placed = plane.project({ x: at, y: at });
    node.position(line.across ? { x: placed.x, y: 0 } : { x: 0, y: placed.y });
    held = { key: line.key, at };
  }

  function drop(line: ZoneLine, event: DragEvent) {
    drag(line, event);
    dragging = false;
    plane.setCursor('grab');
    const at = held?.at;
    if (at === undefined || at === line.saved) {
      held = null;
      return;
    }
    const next = line.rule.at.map((value, index) => (index === line.index ? at : value));
    const saving = onrule?.(line.device, { ...line.rule, at: next });
    if (!saving) {
      held = null;
      return;
    }
    reportFailure(
      saving.catch((error: unknown) => {
        held = null;
        throw error;
      })
    );
  }
</script>

{#if shown !== 'off' && frame && lines.length}
  <Group {...Geometry.screen(plane.view)} listening={false}>
    {#if shown === 'areas'}
      {#each areas as area (area.index)}
        <Rect {...area.rect} fill={hexWithAlpha(plane.colors.zones[area.index % plane.colors.zones.length], 0.07)} />
      {/each}
    {/if}
    {#each lines as line (line.key)}
      {@const inset = 14 + line.stack * 20}
      {#if line.inside}
        <Rect {...line.band} fill={hexWithAlpha(plane.colors.fg, 0.06)} />
        <Line
          points={line.across
            ? [line.at.x, frame.y, line.at.x, frame.y + frame.height]
            : [frame.x, line.at.y, frame.x + frame.width, line.at.y]}
          stroke={plane.colors.fgMuted}
          strokeWidth={1}
          dash={[5, 4]}
          opacity={0.8}
        />
        <Text
          x={line.across ? line.at.x + 6 : frame.x + frame.width - 208}
          y={line.across ? Math.max(frame.y + 7, frame.y + frame.height - 21 - line.stack * 18) : line.at.y - 17}
          width={line.across ? undefined : 200}
          align={line.across ? 'left' : 'right'}
          text={line.value}
          fontSize={11}
          fontFamily={FONT}
          fill={plane.colors.fgMuted}
          opacity={0.75}
        />
      {/if}
      {#if line.inside}
        {#each line.names as name, side (side)}
          <Text
            x={line.across ? (side === 0 ? line.at.x - 206 : line.at.x + 6) : frame.x + 8}
            y={line.across ? frame.y + inset - 7 : side === 0 ? line.at.y + 4 : line.at.y - 18}
            width={line.across ? 200 : undefined}
            align={line.across && side === 0 ? 'right' : 'left'}
            wrap="none"
            text={name}
            fontSize={11}
            fontStyle="500"
            fontFamily={FONT}
            fill={plane.colors.fgMuted}
          />
        {/each}
      {/if}
    {/each}
  </Group>
  {#if canEdit}
    <Group {...Geometry.screen(plane.view)}>
      {#each lines as line (line.key)}
        {#if line.inside}
          <Line
            x={line.across ? line.at.x : 0}
            y={line.across ? 0 : line.at.y}
            points={line.across ? [0, frame.y, 0, frame.y + frame.height] : [frame.x, 0, frame.x + frame.width, 0]}
            stroke="transparent"
            hitStrokeWidth={12}
            draggable
            dragDistance={2}
            onpointerenter={() => plane.setCursor(line.across ? 'ew-resize' : 'ns-resize')}
            onpointerleave={() => !dragging && plane.setCursor('grab')}
            onpointerclick={(event) => (event.cancelBubble = true)}
            ondragstart={(event) => {
              event.cancelBubble = true;
              dragging = true;
            }}
            ondragmove={(event) => drag(line, event)}
            ondragend={(event) => drop(line, event)}
          />
        {/if}
      {/each}
    </Group>
  {/if}
{/if}
