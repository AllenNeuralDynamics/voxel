<script lang="ts">
  import { getVoxelStation } from '$lib/context.svelte';
  import { SpimSession } from '$lib/core/spim.svelte';
  import { Button, Dialog } from '@voxel/kit';

  /**
   * Starts a preview, or stops what a SPIM microscope runs now: the preview at once, an acquisition after it asks.
   * Each window shows it once: on the live profile, or on the app bar while the live profile is in another window.
   * Shows nothing while no SPIM microscope is open. It is as wide as its longest text, so the bar does not shift when
   * the text changes.
   */
  const station = getVoxelStation();
  const spim = $derived(station.sessionOf(SpimSession));
  const acquisition = $derived(spim?.acquisition);
  let asking = $state(false);

  async function stopAcquisition(): Promise<void> {
    asking = false;
    await spim?.stopAcquisition();
  }
</script>

{#if spim}
  {#if acquisition}
    <Button
      variant="danger"
      size="md"
      class="w-42 shrink-0 whitespace-nowrap"
      disabled={acquisition.stopping}
      onclick={() => (asking = true)}
    >
      {acquisition.stopping ? 'Stopping…' : 'Stop acquisition'}
    </Button>
  {:else if spim.previewing}
    <Button variant="danger" size="md" class="w-42 shrink-0 whitespace-nowrap" onclick={() => spim.stopPreview()}
      >Stop</Button
    >
  {:else}
    <Button size="md" class="w-42 shrink-0 whitespace-nowrap" onclick={() => spim.startPreview()}>Preview</Button>
  {/if}

  <Dialog.Root bind:open={asking}>
    <Dialog.Content size="sm" showCloseButton={false}>
      <Dialog.Header>
        <Dialog.Title>Stop the acquisition?</Dialog.Title>
        <Dialog.Description>Volumes that are finished stay on disk. The run is marked as stopped.</Dialog.Description>
      </Dialog.Header>
      <Dialog.Footer>
        <Button size="lg" variant="ghost" onclick={() => (asking = false)}>Cancel</Button>
        <Button size="lg" variant="danger" onclick={stopAcquisition}>Stop acquisition</Button>
      </Dialog.Footer>
    </Dialog.Content>
  </Dialog.Root>
{/if}
