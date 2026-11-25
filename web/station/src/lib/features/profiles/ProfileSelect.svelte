<script lang="ts">
  import { getVoxelStation } from '$lib/context.svelte';
  import { Select } from '@voxel/kit';
  import { displayName } from '@voxel/kit/format';

  /**
   * The profile the open instrument's devices are set to, and the list to pick another. Shows nothing while no
   * instrument is open. Each window shows it once: on the live profile, or on the app bar while the live profile is
   * in another window.
   */
  const station = getVoxelStation();
  const instrument = $derived(station.instrument);
</script>

{#if instrument}
  <Select
    size="md"
    class="w-56 max-w-full shrink"
    prefix="Profile"
    aria-label="Profile"
    value={instrument.activeProfile}
    options={instrument.state.profileIds}
    formatLabel={(id) => instrument.state.profile(id)?.label || displayName(id)}
    onChange={(id) => instrument.selectProfile(id)}
  />
{/if}
