<script lang="ts">
  import type Konva from 'konva';
  import { onMount } from 'svelte';
  import { Shape } from 'svelte-konva';

  import { Prefs } from '$lib/core/prefs';
  import type { SpimTask } from '$lib/core/spim.svelte';

  import { Plane } from './context';
  import type { Point } from './geometry';
  import type { StagePlan } from './stage-plan.svelte';

  let { plan, tasks, color }: { plan: StagePlan; tasks: SpimTask[]; color: string } = $props();

  const plane = Plane.get();
  const shown = $derived(Prefs.stagePaths.get());

  onMount(() =>
    plane.register({
      id: 'paths',
      label: 'Paths',
      menuOrder: 2,
      choices: [
        { value: 'off', label: 'Off' },
        { value: 'within', label: 'Within tasks' },
        { value: 'all', label: 'Whole plan' }
      ],
      get value() {
        return shown;
      },
      setValue: (value) => Prefs.stagePaths.set(value as typeof shown)
    })
  );

  /**
   * The plan's volumes in run order through the middles of their tiles. A move within a task is solid; a move to the
   * next task, or back to a task's first tile for its next profile, is a dashed link.
   */
  const segments = $derived.by(() => {
    const centers = new Map<string, Point>();
    for (const tile of plan.tiles) {
      const key = `${tile.task}:${tile.stop}`;
      if (!centers.has(key)) centers.set(key, tile.center);
    }
    const iteration = new Map(tasks.map((task) => [task.id, task.iteration]));
    const result: { start: Point; end: Point; link: boolean }[] = [];
    let previous: { at: Point; task: string; profile: string } | null = null;
    for (const volume of plan.volumes) {
      const at = centers.get(`${volume.task}:${volume.stop}`);
      if (!at) continue;
      if (previous && (previous.at.x !== at.x || previous.at.y !== at.y)) {
        const link =
          previous.task !== volume.task ||
          (previous.profile !== volume.profile && iteration.get(volume.task) === 'profile_major');
        result.push({ start: previous.at, end: at, link });
      }
      previous = { at, task: volume.task, profile: volume.profile };
    }
    return result;
  });

  const scene = $derived.by(() => {
    const path = shown === 'all' ? segments : segments.filter((segment) => !segment.link);
    const pixel = 1 / plane.view.scale;
    return (drawing: Konva.Context) => {
      if (!path.length) return;
      drawing.setAttr('strokeStyle', color);
      drawing.setAttr('lineWidth', pixel);
      for (const link of [false, true]) {
        drawing.setLineDash(link ? [4 * pixel, 4 * pixel] : []);
        drawing.beginPath();
        for (const { start, end } of path.filter((segment) => segment.link === link)) {
          drawing.moveTo(start.x, start.y);
          drawing.lineTo(end.x, end.y);
        }
        drawing.stroke();
      }
      drawing.setLineDash([]);
      drawing.setAttr('fillStyle', color);
      for (const { start, end } of path) {
        const dx = end.x - start.x;
        const dy = end.y - start.y;
        const length = Math.hypot(dx, dy);
        if (length < 18 * pixel) continue;
        const x = (start.x + end.x) / 2;
        const y = (start.y + end.y) / 2;
        const cos = dx / length;
        const sin = dy / length;
        const arm = 3.5 * pixel;
        drawing.beginPath();
        drawing.moveTo(x + arm * cos, y + arm * sin);
        drawing.lineTo(x - arm * cos - arm * sin * 0.85, y - arm * sin + arm * cos * 0.85);
        drawing.lineTo(x - arm * cos + arm * sin * 0.85, y - arm * sin - arm * cos * 0.85);
        drawing.closePath();
        drawing.fill();
      }
    };
  });
</script>

{#if shown !== 'off' && segments.length}
  <Shape sceneFunc={scene} listening={false} perfectDrawEnabled={false} />
{/if}
