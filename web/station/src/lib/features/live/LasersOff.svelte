<script lang="ts">
  import { getVoxelStation } from '$lib/context.svelte';
  import { Button } from '@voxel/kit';

  /**
   * Turns off every laser and modulator of the open instrument, and closes every shutter. Each window shows it once,
   * at its bottom right: on the live profile's bar, or on the Diagnostics bar while the live profile is in another
   * window. Disabled while no instrument is open.
   */
  const station = getVoxelStation();
</script>

<Button
  variant="danger"
  size="xs"
  class="shrink-0"
  disabled={!station.session}
  onclick={() => station.session?.lasersOff()}>Lasers off</Button
>
