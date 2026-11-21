<script lang="ts">
  import { getVoxelStation } from '$lib/context.svelte';
  import { useShortcut } from '$lib/shell/shortcuts';
  import { Button, Dialog } from '@voxel/kit';
  import { displayName } from '@voxel/kit/format';

  import type { InstrumentSelection } from './selection.svelte';

  /** Asks before the open instrument closes, alone or to switch to another instrument. */
  let { selection }: { selection: InstrumentSelection } = $props();

  const app = getVoxelStation();
  const openName = $derived(displayName(app.activeName ?? 'the active instrument'));

  useShortcut('closeInstrument', () => {
    if (app.instrument) selection.askToClose();
  });
</script>

<Dialog.Root bind:open={selection.dialogOpen}>
  <Dialog.Content size="sm" showCloseButton={false}>
    <Dialog.Header>
      <Dialog.Title>{selection.pending ? 'Switch instrument?' : 'Close instrument?'}</Dialog.Title>
      <Dialog.Description>
        {#if selection.pending}
          Close <span class="font-medium text-fg">{openName}</span> and
          {selection.pending.open ? 'open' : 'inspect'}
          <span class="font-medium text-fg">{displayName(selection.pending.instrumentId)}</span>? The current
          instrument's hardware will be disconnected.
        {:else}
          Are you sure you want to close <span class="font-medium text-fg">{openName}</span>? Its hardware will be
          disconnected.
        {/if}
      </Dialog.Description>
    </Dialog.Header>
    <Dialog.Footer>
      <Button size="lg" variant="ghost" disabled={selection.closing} onclick={() => selection.cancel()}>Cancel</Button>
      <Button size="lg" variant="danger" disabled={selection.closing} onclick={() => selection.confirm()}>
        {selection.closing ? 'Closing…' : selection.pending ? 'Close and switch' : 'Close instrument'}
      </Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
