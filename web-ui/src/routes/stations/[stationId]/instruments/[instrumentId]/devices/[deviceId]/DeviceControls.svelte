<script lang="ts">
  import { CameraHandle, type DeviceHandle, type Instrument, LaserHandle } from '$lib/model';

  import CameraControls from './CameraControls.svelte';
  import GenericCommands from './GenericCommands.svelte';
  import GenericProperties from './GenericProperties.svelte';
  import LaserControls from './LaserControls.svelte';

  interface Props {
    device: DeviceHandle;
    instrument?: Instrument | null;
  }

  const { device, instrument }: Props = $props();
  const propertyCount = $derived(Object.keys(device.interface?.properties ?? {}).length);
</script>

{#if device instanceof CameraHandle}
  <CameraControls camera={device} {instrument} />
{:else if device instanceof LaserHandle && instrument}
  <LaserControls laser={device} {instrument} />
{:else}
  <section>
    <h3 class="mb-3 text-sm font-medium text-fg-muted">Properties</h3>
    {#if propertyCount > 0}
      <GenericProperties {device} instrument={instrument ?? undefined} />
    {:else}
      <p class="text-fg-muted">This device does not expose any live properties.</p>
    {/if}
  </section>

  <GenericCommands {device} />
{/if}
