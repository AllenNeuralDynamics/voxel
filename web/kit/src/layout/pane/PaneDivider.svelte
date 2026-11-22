<script lang="ts">
  import { PaneResizer } from 'paneforge';

  import { cn } from '../../utils/cn';

  interface Split {
    /** Length along the divider, as CSS. A split without it takes the space left. */
    size?: string;
    /** Space without line at each end of the split, as CSS. */
    gap?: string;
  }

  interface Props {
    /** Parts of the line, from the top or the left. The whole divider can be dragged, gaps too. */
    splits?: Split[];
    ondblclick?: () => void;
  }

  let { splits = [{}], ondblclick }: Props = $props();
  // The line runs across its group's direction: up and down between panes side by side, left to right between
  // stacked panes. paneforge marks the divider with its group's direction (`data-direction`).
</script>

<PaneResizer class="group/divider relative z-50" {ondblclick}>
  <div
    class="absolute flex group-data-[direction=horizontal]/divider:inset-y-0 group-data-[direction=horizontal]/divider:left-1/2 group-data-[direction=horizontal]/divider:-translate-x-1/2 group-data-[direction=horizontal]/divider:flex-col group-data-[direction=horizontal]/divider:px-1 group-data-[direction=vertical]/divider:inset-x-0 group-data-[direction=vertical]/divider:top-1/2 group-data-[direction=vertical]/divider:-translate-y-1/2 group-data-[direction=vertical]/divider:py-1"
  >
    {#each splits as split, index (index)}
      <div
        class={cn(
          'bg-line bg-clip-content transition-colors duration-300 group-hover/divider:bg-accent-fg group-data-[direction=horizontal]/divider:w-px group-data-[direction=horizontal]/divider:py-(--split-gap) group-data-[direction=vertical]/divider:h-px group-data-[direction=vertical]/divider:px-(--split-gap)',
          split.size === undefined ? 'flex-1' : 'shrink-0'
        )}
        style:flex-basis={split.size}
        style:--split-gap={split.gap}
      ></div>
    {/each}
  </div>
</PaneResizer>
