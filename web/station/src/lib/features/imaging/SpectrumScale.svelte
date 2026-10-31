<script lang="ts">
  import { cn } from '@voxel/kit/cn';

  import { xAt } from './channels';

  interface Props {
    /** Lines the scale up with tile spectra; without it, with edge-to-edge ones. */
    inset?: boolean;
  }

  let { inset = true }: Props = $props();

  const SCALE_MARKS = [400, 500, 600, 700, 800];
</script>

<div class={cn('relative h-4 text-xs text-fg-faint tabular-nums', inset && 'mx-3')} aria-hidden="true">
  {#each SCALE_MARKS as nm (nm)}
    <span class="absolute -translate-x-1/2" style:left={`${xAt(nm)}%`}>{nm}</span>
  {/each}
</div>
