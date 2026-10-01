<script lang="ts">
  import { createHotkey } from '@tanstack/svelte-hotkeys';

  import AcquisitionDialog from '$lib/AcquisitionDialog.svelte';
  import { Button, Spinner } from '$lib/kit';
  import type { Instrument, Station } from '$lib/model';
  import { getPreviewContext } from '$lib/preview/session.svelte';
  import { cn, toastError } from '$lib/utils';

  interface Props {
    app: Station;
    class?: string;
  }

  type Operation = 'start-preview' | 'stop-preview' | 'stop-acquisition';
  interface PendingRequest {
    instrument: Instrument;
    operation: Operation;
  }

  let { app, class: className }: Props = $props();

  const previews = getPreviewContext();
  const instrument = $derived(app.instrument);
  const preview = $derived(previews.current);
  const confirmedMode = $derived<'preview' | 'acquire' | null>(
    instrument?.mode === 'capture' ? 'acquire' : instrument?.mode === 'preview' ? 'preview' : null
  );
  let pendingRequest = $state.raw<PendingRequest | null>(null);
  let dialogOpen = $state(false);

  // HTTP progress takes precedence over the live mode until the request completes.
  // A request for a previous instrument must not affect the current controls.
  const pendingOperation = $derived(pendingRequest?.instrument === instrument ? pendingRequest?.operation : undefined);
  const busy = $derived(pendingOperation !== undefined);
  const previewLoading = $derived(pendingOperation === 'start-preview' || pendingOperation === 'stop-preview');
  const acquisitionLoading = $derived(pendingOperation === 'stop-acquisition');
  const hasVisibleChannels = $derived(preview?.channels.some((channel) => channel.visible) ?? false);
  const previewDisabled = $derived(
    !instrument || !preview || busy || confirmedMode === 'acquire' || (confirmedMode === null && !hasVisibleChannels)
  );
  const acquisitionDisabled = $derived(!instrument || busy || confirmedMode === 'preview');
  const previewLabel = $derived(
    pendingOperation === 'start-preview'
      ? 'Starting preview…'
      : pendingOperation === 'stop-preview'
        ? 'Stopping preview…'
        : confirmedMode === 'preview'
          ? 'Stop Preview'
          : 'Preview'
  );
  const acquisitionLabel = $derived(
    acquisitionLoading ? 'Stopping…' : confirmedMode === 'acquire' ? 'Stop Acquisition' : 'Acquire'
  );
  const expandedControl = $derived(previewLoading ? 'preview' : confirmedMode);
  const columns = $derived(
    expandedControl === 'preview' ? '1fr 0fr' : expandedControl === 'acquire' ? '0fr 1fr' : '1fr 1fr'
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
    if (previewDisabled || !instrument || !session) return;
    const stopping = confirmedMode === 'preview';
    toastError(
      runOperation(instrument, stopping ? 'stop-preview' : 'start-preview', () =>
        stopping ? session.stopPreview() : session.startPreview()
      )
    );
  }

  function toggleAcquisition(): void {
    const target = instrument;
    if (acquisitionDisabled || !target) return;
    if (confirmedMode !== 'acquire') {
      dialogOpen = true;
      return;
    }
    toastError(runOperation(target, 'stop-acquisition', () => target.stopAcquisition()));
  }

  // Mouse and keyboard share the same guards and error handling.
  createHotkey('Alt+P', togglePreview);
</script>

<div class={cn('flex items-center gap-2', className)}>
  <div class="w-full">
    <div class="grid transition-[grid-template-columns] duration-300 ease-out" style="grid-template-columns: {columns}">
      <div class={cn('overflow-hidden', confirmedMode === 'acquire' && 'pointer-events-none')}>
        <Button
          variant={confirmedMode === 'preview' ? 'danger' : 'secondary'}
          size="md"
          class={cn('w-full whitespace-nowrap', expandedControl === null && 'rounded-r-none border-control-line')}
          disabled={previewDisabled}
          aria-busy={previewLoading}
          onclick={togglePreview}
        >
          {#if previewLoading}<Spinner aria-hidden="true" />{/if}
          {previewLabel}
        </Button>
      </div>
      <div class={cn('overflow-hidden', confirmedMode === 'preview' && 'pointer-events-none')}>
        <Button
          variant={confirmedMode === 'acquire' ? 'danger' : 'secondary'}
          size="md"
          class={cn(
            'w-full whitespace-nowrap',
            expandedControl === null && 'rounded-l-none border-l-0 border-control-line'
          )}
          disabled={acquisitionDisabled}
          aria-busy={acquisitionLoading}
          onclick={toggleAcquisition}
        >
          {#if acquisitionLoading}<Spinner aria-hidden="true" />{/if}
          {acquisitionLabel}
        </Button>
      </div>
    </div>
  </div>
</div>

<AcquisitionDialog {app} bind:open={dialogOpen} />
