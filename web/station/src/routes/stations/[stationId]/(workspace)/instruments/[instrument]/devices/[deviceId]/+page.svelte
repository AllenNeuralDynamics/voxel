<script lang="ts">
  import { page } from '$app/state';
  import { getInstrumentSelection, useAppBar } from '$lib/context.svelte';
  import DevicePanel from '$lib/features/devices/DevicePanel.svelte';
  import PartPanel from '$lib/features/devices/PartPanel.svelte';
  import { displayName } from '@voxel/kit/format';

  const selection = getInstrumentSelection();
  const name = $derived(page.params.instrument ?? '');
  const id = $derived(page.params.deviceId ?? '');

  useAppBar(() => ({
    crumbs: [{ label: 'Devices', href: selection.href(name, 'devices') }, { label: displayName(id) }]
  }));
</script>

<div class="h-full page-body pt-4">
  {#if selection.instrument?.config?.parts[id]}
    <PartPanel {id} />
  {:else}
    <DevicePanel {id} />
  {/if}
</div>
