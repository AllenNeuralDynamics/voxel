<script lang="ts">
  import { getVoxelStation } from '$lib/context.svelte';
  import { AreaCamera } from '$lib/core/device.svelte';
  import { displayName } from '@voxel/kit/format';

  /** How each camera's stream runs: its frame rate, the frames it dropped, and its data rate. */
  const station = getVoxelStation();
  const cameras = $derived(station.session?.devicesOf(AreaCamera) ?? []);
  // The last column is wider by the inset of a block's text: its name ends on the blocks' edge, and its values are
  // inset from that.
  const columns = 'grid grid-cols-[minmax(0,1fr)_5rem_4.5rem_6.125rem]';
</script>

<section class="flex h-full min-h-0 flex-col" aria-label="Stream">
  <!-- The heading's row has the columns of the rows under it, so each column's name is above its values, and the row's ends are on the blocks' edges. The names
  here are for the eye; the table has its own for screen readers. -->
  <div class={[columns, 'px-inset mt-1.5 mb-1 h-ui-md shrink-0 items-center gap-x-2 text-sm']}>
    <h3 class="font-medium text-fg-muted">Stream</h3>
    <span class="text-right text-fg-faint" aria-hidden="true">Frame rate</span>
    <span class="text-right text-fg-faint" aria-hidden="true">Dropped</span>
    <span class="text-right text-fg-faint" aria-hidden="true">Data rate</span>
  </div>
  <div class="px-inset min-h-0 flex-1 overflow-y-auto pb-2">
    <!-- The blocks' edges are on the pane's inset; the text in them is inset from that. -->
    <div role="table" aria-label="Streams" class={[columns, 'relative gap-x-2 gap-y-1.5 text-sm tabular-nums']}>
      <div role="row" class="sr-only">
        <span role="columnheader">Camera</span>
        <span role="columnheader">Frame rate</span>
        <span role="columnheader">Dropped</span>
        <span role="columnheader">Data rate</span>
      </div>
      {#each cameras as camera (camera.id)}
        {@const stream = camera.streamInfo}
        <div role="row" class="col-span-4 grid grid-cols-subgrid rounded-md bg-tint py-1.5 pl-2.5">
          <span role="rowheader" class="truncate" title={displayName(camera.id)}>{displayName(camera.id)}</span>
          <span role="cell" class="text-right">{stream ? `${stream.frame_rate_fps.toFixed(1)} fps` : '–'}</span>
          <span role="cell" class={['text-right', stream && stream.dropped_frames > 0 && 'text-warning-fg']}>
            {stream ? stream.dropped_frames : '–'}
          </span>
          <span role="cell" class="pr-2.5 text-right">{stream ? `${stream.data_rate_mbs.toFixed(1)} MB/s` : '–'}</span>
        </div>
      {/each}
    </div>
  </div>
</section>
