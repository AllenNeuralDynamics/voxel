<script lang="ts">
  import { CameraHandle, type DeviceHandle } from '$lib/model';

  import CameraControls from './CameraControls.svelte';
  import GenericCommands from './GenericCommands.svelte';
  import GenericProperties from './GenericProperties.svelte';

  interface Props {
    device: DeviceHandle;
  }

  const { device }: Props = $props();
  const propertyCount = $derived(Object.keys(device.interface?.properties ?? {}).length);
</script>

{#if device instanceof CameraHandle}
  <CameraControls camera={device} />
{:else}
  <section>
    <h3 class="mb-3 text-sm font-medium text-fg-muted">Properties</h3>
    {#if propertyCount > 0}
      <GenericProperties {device} />
    {:else}
      <p class="text-fg-muted">This device does not expose any live properties.</p>
    {/if}
  </section>

  <GenericCommands {device} />
{/if}
