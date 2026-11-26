<script lang="ts">
  import { onMount } from 'svelte';
  import { Group, Line } from 'svelte-konva';

  import { Prefs } from '$lib/core/prefs';
  import type { RunRecord } from '$lib/core/station.svelte';
  import type { SpecimenAxis } from '$lib/core/types';
  import { hexWithAlpha } from '@voxel/kit/colors';

  import { Plane } from './context';
  import { Geometry, type Point } from './geometry';

  interface Props {
    run: RunRecord | undefined;
    /** The stage axes across and up the map. */
    h: SpecimenAxis;
    v: SpecimenAxis;
    /** While a run goes, the record is that run, which the task tiles already show. */
    hidden?: boolean;
  }

  let { run, h, v, hidden = false }: Props = $props();

  const plane = Plane.get();
  const shown = $derived(Prefs.stageLastRun.get());

  onMount(() =>
    plane.register({
      id: 'last-run',
      label: 'Last run',
      menuOrder: 1.5,
      get visible() {
        return shown;
      },
      setVisible: (value) => Prefs.stageLastRun.set(value)
    })
  );

  // Each image's reach on the map: its frame swept through all its frames. Images at 1 place are 1 area, done only
  // when every visit there completed.
  const areas = $derived.by(() => {
    const found = new Map<string, { points: Point[]; done: boolean }>();
    for (const visit of run?.visits ?? []) {
      for (const cameras of Object.values(visit.channels)) {
        for (const { transform } of Object.values(cameras)) {
          const [frames, rows, columns] = transform.shape;
          const [frame, row, column] = transform.steps;
          const corners: Point[] = [];
          for (const f of [0, Math.max(frames - 1, 0)])
            for (const r of [-0.5, rows - 0.5])
              for (const c of [-0.5, columns - 0.5]) {
                const at = (axis: SpecimenAxis) =>
                  transform.origin[axis] + f * frame[axis] + r * row[axis] + c * column[axis];
                corners.push({ x: at(h), y: at(v) });
              }
          const points = Geometry.hull(corners);
          const key = points.map((point) => `${point.x.toFixed(2)},${point.y.toFixed(2)}`).join(' ');
          const done = visit.result === 'completed' && (found.get(key)?.done ?? true);
          found.set(key, { points, done });
        }
      }
    }
    return [...found.entries()].map(([key, area]) => ({ key, ...area }));
  });
</script>

{#if shown && !hidden && areas.length}
  <Group {...Geometry.world(plane.view.scale)} listening={false}>
    {#each areas as area (area.key)}
      <Line
        points={area.points.flatMap((point) => [point.x, point.y])}
        closed
        fill={area.done ? hexWithAlpha(plane.colors.success, 0.1) : hexWithAlpha(plane.colors.warning, 0.22)}
        perfectDrawEnabled={false}
      />
    {/each}
  </Group>
{/if}
