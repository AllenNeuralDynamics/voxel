<script lang="ts">
  import { PaneResizer } from 'paneforge';

  import { cn } from '$lib/core/utils';

  interface Split {
    /** Length along the divider, as CSS. A split without it takes the space left. */
    size?: string;
    /** Space without line at each end of the split, as CSS. */
    gap?: string;
  }

  interface Props {
    direction?: 'vertical' | 'horizontal';
    /** Parts of the line, from the top or the left. The whole divider can be dragged, gaps too. */
    splits?: Split[];
    ondblclick?: () => void;
  }

  let { direction = 'vertical', splits = [{}], ondblclick }: Props = $props();
</script>

<PaneResizer class="relative z-50" {ondblclick}>
  <div
    class={cn(
      'group/divider absolute flex',
      direction === 'vertical'
        ? 'inset-y-0 left-1/2 -translate-x-1/2 flex-col px-1'
        : 'inset-x-0 top-1/2 -translate-y-1/2 py-1'
    )}
  >
    {#each splits as split, index (index)}
      <div
        class={cn(
          'bg-line bg-clip-content transition-colors duration-300 group-hover/divider:bg-accent-fg',
          direction === 'vertical' ? 'w-px' : 'h-px',
          split.size === undefined ? 'flex-1' : 'shrink-0'
        )}
        style:flex-basis={split.size}
        style:padding-block={direction === 'vertical' ? split.gap : undefined}
        style:padding-inline={direction === 'vertical' ? undefined : split.gap}
      ></div>
    {/each}
  </div>
</PaneResizer>
