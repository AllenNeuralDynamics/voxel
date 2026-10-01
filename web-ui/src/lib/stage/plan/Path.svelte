<script lang="ts">
  import type Konva from 'konva';
  import { onMount } from 'svelte';
  import { Shape } from 'svelte-konva';

  import type { PlannedVolume } from '$lib/model';
  import { pref } from '$lib/utils';

  import { getStageContext } from '../context.svelte';
  import type { Point } from '../geometry';

  let {
    volumes,
    taskVisible,
    color
  }: {
    volumes: readonly PlannedVolume[];
    taskVisible: (task: string) => boolean;
    color: string;
  } = $props();

  const context = getStageContext();
  const visibility = pref('stage:acquisition-path-visible', true);
  const points = $derived.by(() => {
    const result: (Point & { task: string })[] = [];
    for (const { task, x, y } of volumes) {
      const previous = result.at(-1);
      if (!previous || previous.task !== task || previous.x !== x || previous.y !== y) result.push({ task, x, y });
    }
    return result;
  });
  const segments = $derived(
    points.slice(1).flatMap((end, index) => {
      const start = points[index];
      return taskVisible(start.task) && taskVisible(end.task) ? [{ start, end }] : [];
    })
  );
  const scene = $derived.by(() => {
    const path = segments;
    const stroke = color;
    const pixel = 1 / context.view.scale;
    return (drawing: Konva.Context) => {
      if (!path.length) return;
      drawing.setAttr('strokeStyle', stroke);
      drawing.setAttr('lineWidth', 1.25 * pixel);
      drawing.setAttr('globalAlpha', 0.2);
      drawing.beginPath();
      for (const { start, end } of path) {
        drawing.moveTo(start.x, start.y);
        drawing.lineTo(end.x, end.y);
      }
      drawing.stroke();

      drawing.setAttr('globalAlpha', 0.32);
      drawing.beginPath();
      for (const { start, end } of path) {
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

  onMount(() =>
    context.register({
      id: 'acquisition-path',
      label: 'Acquisition path',
      menuOrder: 2,
      get visible() {
        return visibility.get();
      },
      setVisible: visibility.set
    })
  );
</script>

{#if visibility.get() && segments.length}
  <Shape staticConfig sceneFunc={scene} listening={false} perfectDrawEnabled={false} />
{/if}
