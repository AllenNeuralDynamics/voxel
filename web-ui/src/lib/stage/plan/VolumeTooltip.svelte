<script lang="ts">
  import { Group, Line, Rect, Text } from 'svelte-konva';

  import { hexWithAlpha } from '$lib/colors.svelte';
  import { themes } from '$lib/themes/manager.svelte';

  import { getStageContext } from '../context.svelte';
  import { screenTransform } from '../geometry';

  interface TooltipVolume {
    order: number;
    taskOrder: number | undefined;
  }

  let { volumes }: { volumes: readonly TooltipVolume[] } = $props();

  const context = getStageContext();
  const color = $derived(themes.resolvedMode === 'light' ? '#52525b' : '#d4d4d8');
  const background = $derived(themes.resolvedMode === 'light' ? '#ffffff' : '#18181b');
  const rowHeight = 20;
  const shown = $derived(volumes.slice(0, 5));
  const remaining = $derived(volumes.length - shown.length);
  const numberWidth = $derived(8 + Math.max(1, ...shown.map(({ order }) => String(order).length)) * 7.5);
  const taskWidth = $derived(Math.max(0, ...shown.map(({ taskOrder }) => `Task ${taskOrder ?? ''}`.length)) * 7.5);
  const taskX = $derived(8 + numberWidth + 10);
  const width = $derived(Math.min(context.view.width - 8, taskX + taskWidth + 8));
  const height = $derived(12 + shown.length * rowHeight + (remaining ? 24 : 0));
  const cursor = $derived(context.cursor ? context.project(context.cursor) : null);
  const x = $derived(cursor ? Math.max(4, Math.min(cursor.x + 12, context.view.width - width - 4)) : 0);
  const y = $derived(cursor ? Math.max(4, Math.min(cursor.y + 12, context.view.height - height - 4)) : 0);
</script>

{#if cursor && shown.length}
  <Group {...screenTransform(context.view)}>
    <Group {x} {y} listening={false}>
      <Rect {width} {height} fill={background} stroke={hexWithAlpha(color, 0.25)} strokeWidth={1} cornerRadius={4} />
      {#each shown as volume, index (volume.order)}
        {@const rowY = 6 + index * rowHeight}
        <Text
          x={8}
          y={rowY}
          width={numberWidth}
          height={rowHeight}
          text={`#${volume.order}`}
          align="left"
          verticalAlign="middle"
          fontSize={12}
          fontFamily="monospace"
          fill={color}
        />
        <Text
          x={taskX}
          y={rowY}
          width={taskWidth}
          height={rowHeight}
          text={volume.taskOrder === undefined ? '' : `Task ${volume.taskOrder}`}
          verticalAlign="middle"
          fontSize={12}
          fontFamily="monospace"
          fill={hexWithAlpha(color, 0.68)}
        />
      {/each}
      {#if remaining}
        <Line
          points={[8, 9 + shown.length * rowHeight, width - 8, 9 + shown.length * rowHeight]}
          stroke={hexWithAlpha(color, 0.2)}
          strokeWidth={1}
        />
        <Text
          x={8}
          y={12 + shown.length * rowHeight}
          width={width - 16}
          height={18}
          text={`+${remaining} more`}
          verticalAlign="middle"
          fontSize={12}
          fontFamily="sans-serif"
          fill={hexWithAlpha(color, 0.68)}
        />
      {/if}
    </Group>
  </Group>
{/if}
