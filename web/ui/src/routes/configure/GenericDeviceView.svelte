<script lang="ts">
  import type { Microscope } from '$lib/microscope';
  import type { PropertyInfo } from '$lib/protocol/device';
  import { DeviceHeader, PropRow } from './components.svelte';

  interface Props {
    microscope: Microscope;
    deviceId: string;
  }

  let { microscope, deviceId }: Props = $props();

  const device = $derived(microscope.get(deviceId));
  const deviceType = $derived(device?.interface?.type ?? 'device');

  const writableProps = $derived.by<Array<[string, PropertyInfo]>>(() => {
    const iface = device?.interface;
    if (!iface) return [];
    return Object.entries(iface.properties).filter(([name, info]) => info.access === 'rw' && name !== 'roi');
  });

  const saved = $derived(microscope.profiles.savedProps(deviceId));
</script>

{@render DeviceHeader(deviceId, deviceType)}
{#if !device || writableProps.length === 0}
  <div class="col-span-3 text-xs text-fg-faint italic">no writable properties</div>
{:else}
  {#each writableProps as [propName, info] (propName)}
    {@render PropRow(device, propName, info, saved?.[propName])}
  {/each}
{/if}
