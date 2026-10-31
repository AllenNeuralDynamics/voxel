<script lang="ts">
  import { getPreviewContext, getVoxelStation } from '$lib/context.svelte';
  import { type Instrument } from '$lib/core/model';
  import { useShortcut } from '$lib/shell/shortcuts';
  import { Button, Dialog, Spinner } from '@voxel/kit';
  import { cn } from '@voxel/kit/cn';
  import { reportFailure } from '@voxel/kit/failures';

  interface Props {
    class?: string;
  }

  type Operation = 'start-preview' | 'stop-preview' | 'stop-acquisition';
  interface PendingRequest {
    instrument: Instrument;
    operation: Operation;
  }

  let { class: className }: Props = $props();

  const app = getVoxelStation();
  const previews = getPreviewContext();
  const instrument = $derived(app.instrument);
  const preview = $derived(previews.current);
  const confirmedRun = $derived<'preview' | 'acquire' | null>(
    instrument?.activity.kind === 'capture' ? 'acquire' : instrument?.activity.kind === 'preview' ? 'preview' : null
  );
  let pendingRequest = $state.raw<PendingRequest | null>(null);
  let stopOpen = $state(false);

  // A request for a previous instrument must not affect the current controls.
  const pendingOperation = $derived(pendingRequest?.instrument === instrument ? pendingRequest?.operation : undefined);
  const busy = $derived(pendingOperation !== undefined);
  const acquiring = $derived(confirmedRun === 'acquire');
  const hasPreviewChannels = $derived((instrument?.previewChannels.length ?? 0) > 0);
  const disabled = $derived(
    !instrument || busy || (!acquiring && (!preview || (confirmedRun === null && !hasPreviewChannels)))
  );
  const label = $derived(
    pendingOperation === 'start-preview'
      ? 'Starting preview…'
      : pendingOperation === 'stop-preview'
        ? 'Stopping preview…'
        : pendingOperation === 'stop-acquisition'
          ? 'Stopping…'
          : acquiring
            ? 'Stop acquisition'
            : confirmedRun === 'preview'
              ? 'Stop preview'
              : 'Preview'
  );

  async function runOperation(target: Instrument, operation: Operation, perform: () => Promise<void>): Promise<void> {
    const request = { instrument: target, operation };
    pendingRequest = request;
    try {
      await perform();
    } finally {
      // A completed request must not clear a newer instrument's pending request.
      if (pendingRequest === request) pendingRequest = null;
    }
  }

  function togglePreview(): void {
    const session = preview;
    if (disabled || acquiring || !instrument || !session) return;
    const stopping = confirmedRun === 'preview';
    reportFailure(
      runOperation(instrument, stopping ? 'stop-preview' : 'start-preview', () =>
        stopping ? session.stopPreview() : session.startPreview()
      )
    );
  }

  function stopAcquisition(): void {
    stopOpen = false;
    const target = instrument;
    if (!target) return;
    reportFailure(runOperation(target, 'stop-acquisition', () => target.stopAcquisition()));
  }

  // An acquisition starts on the Run page.
  function press(): void {
    if (acquiring) stopOpen = true;
    else togglePreview();
  }

  useShortcut('togglePreview', togglePreview);
</script>

<Button
  variant={confirmedRun ? 'danger' : 'default'}
  size="md"
  class={cn('w-42 whitespace-nowrap', className)}
  {disabled}
  aria-busy={busy}
  onclick={press}
>
  {#if busy}<Spinner aria-hidden="true" />{/if}
  {label}
</Button>

<Dialog.Root bind:open={stopOpen}>
  <Dialog.Content size="sm" showCloseButton={false}>
    <Dialog.Header>
      <Dialog.Title>Stop the acquisition?</Dialog.Title>
      <Dialog.Description>Volumes that are finished stay on disk. The run is marked as stopped.</Dialog.Description>
    </Dialog.Header>
    <Dialog.Footer>
      <Button size="lg" variant="ghost" onclick={() => (stopOpen = false)}>Cancel</Button>
      <Button size="lg" variant="danger" onclick={stopAcquisition}>Stop acquisition</Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
