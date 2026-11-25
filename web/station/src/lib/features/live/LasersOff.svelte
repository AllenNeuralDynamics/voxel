<script lang="ts">
  import { getVoxelStation } from '$lib/context.svelte';
  import { Button } from '@voxel/kit';

  /** Turns off every laser and modulator and closes every shutter. */
  const station = getVoxelStation();
</script>

<Button
  variant="danger"
  size="xs"
  class="shrink-0"
  disabled={!station.session}
  onclick={() => station.session?.lasersOff()}>Lasers off</Button
>
