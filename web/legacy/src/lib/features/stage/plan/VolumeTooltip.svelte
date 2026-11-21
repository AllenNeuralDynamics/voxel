<script lang="ts">
  import { Group, Line, Rect, Text } from 'svelte-konva';

  import { watchTheme } from '@voxel/kit/style';

  import { getStageContext } from '../context';
  import { screenTransform } from '../geometry';

  interface TooltipVolume {
    order: number;
    taskOrder: number | undefined;
  }

  let { volumes }: { volumes: readonly TooltipVolume[] } = $props();

  const context = getStageContext();
  let look = $state({ background: '', ring: '', text: '', muted: '' });
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

  // The frame-floating colors, read as values because a canvas cannot use CSS.
  watchTheme(() => {
    const styles = getComputedStyle(document.documentElement);
    const read = (name: string) => styles.getPropertyValue(name).trim();
    look = {
      background: read('--floating'),
      ring: read('--line-faint'),
      text: read('--fg'),
      muted: read('--fg-muted')
    };
  });
</script>

{#if cursor && shown.length}
  <Group {...screenTransform(context.view)}>
    <Group {x} {y} listening={false}>
      <Rect {width} {height} fill={look.background} stroke={look.ring} strokeWidth={1} cornerRadius={4} />
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
          fill={look.text}
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
          fill={look.muted}
        />
      {/each}
      {#if remaining}
        <Line
          points={[8, 9 + shown.length * rowHeight, width - 8, 9 + shown.length * rowHeight]}
          stroke={look.ring}
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
          fill={look.muted}
        />
      {/if}
    </Group>
  </Group>
{/if}
