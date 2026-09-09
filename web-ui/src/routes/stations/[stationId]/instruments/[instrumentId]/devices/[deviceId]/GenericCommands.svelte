<script lang="ts">
  import type { DeviceHandle } from '$lib/model';

  import DeviceCommandButton from './DeviceCommandButton.svelte';

  interface Props {
    device: DeviceHandle;
    exclude?: string[];
  }

  const { device, exclude = [] }: Props = $props();
  const commandNames = $derived(
    Object.keys(device.interface?.commands ?? {}).filter((name) => !exclude.includes(name))
  );
</script>

<section>
  <h3 class="mb-3 text-sm font-medium text-fg-muted">Commands</h3>
  {#if commandNames.length > 0}
    <div class="grid grid-cols-[repeat(auto-fill,minmax(12rem,1fr))] gap-2">
      {#each commandNames as commandName (commandName)}
        <DeviceCommandButton {device} {commandName} />
      {/each}
    </div>
  {:else}
    <p class="text-fg-muted">This device does not expose any commands.</p>
  {/if}
</section>
