<script lang="ts">
  import { getVoxelStation } from '$lib/context.svelte';
  import { Select } from '@voxel/kit';
  import { displayName } from '@voxel/kit/format';

  /** Active profile picker; rendered once per window, on the live profile or else on the app bar. */
  const station = getVoxelStation();
  const session = $derived(station.session);
</script>

{#if session}
  <Select
    size="md"
    class="w-56 max-w-full shrink"
    prefix="Profile"
    aria-label="Profile"
    value={session.activeProfile}
    options={session.instrument.state.profileIds}
    formatLabel={(id) => session.instrument.state.profile(id)?.label || displayName(id)}
    onChange={(id) => session.selectProfile(id)}
  />
{/if}
