<script lang="ts">
  import { watch } from 'runed';

  import AcquisitionDialog from '$lib/AcquisitionDialog.svelte';
  import { Button } from '$lib/kit';
  import type { VoxelApp } from '$lib/model';
  import { cn, toastError } from '$lib/utils';

  interface Props {
    app: VoxelApp;
    class?: string;
  }

  let { app, class: className }: Props = $props();

  const instrument = $derived(app.instrument);
  const canPreview = $derived(instrument?.preview.channels.some((c) => c.visible) ?? false);
  const canAcquire = $derived((instrument?.taskTiles.length ?? 0) > 0);

  // Which action fills the control: null = idle split, 'preview'/'acquire' = full-width Stop.
  const modeActive = $derived<'preview' | 'acquire' | null>(
    instrument?.mode === 'capture' ? 'acquire' : instrument?.mode === 'preview' ? 'preview' : null
  );

  // Optimistic override so the grow animates on click, before the server confirms the mode flip.
  // `undefined` = follow the server; a set value wins until the server catches up (or the fallback fires).
  let override = $state<'preview' | 'acquire' | null | undefined>(undefined);
  let overrideTimer: number | null = null;
  const active = $derived(override !== undefined ? override : modeActive);

  let dialogOpen = $state(false);

  function setOptimistic(next: 'preview' | 'acquire' | null): void {
    override = next;
    if (overrideTimer !== null) clearTimeout(overrideTimer);
    overrideTimer = window.setTimeout(() => (override = undefined), 1500); // fall back to server truth if it never confirms
  }

  // Once the server's mode matches our optimistic guess, stop overriding and track it.
  watch(
    () => modeActive,
    (m) => {
      if (override !== undefined && m === override) {
        override = undefined;
        if (overrideTimer !== null) clearTimeout(overrideTimer);
      }
    }
  );

  function togglePreview(): void {
    if (!instrument) return;
    if (active === 'preview') {
      setOptimistic(null);
      instrument.preview.stopPreview();
    } else {
      setOptimistic('preview');
      instrument.preview.startPreview();
    }
  }

  function toggleAcquire(): void {
    if (!instrument) return;
    if (active === 'acquire') {
      setOptimistic(null);
      toastError(instrument.stopAcquisition());
    } else {
      dialogOpen = true; // the dialog's Start begins capture; the grow follows mode → 'capture'
    }
  }

  const cols = $derived(active === 'preview' ? '1fr 0fr' : active === 'acquire' ? '0fr 1fr' : '1fr 1fr');
</script>

<div class={cn('w-56', className)}>
  <div class="grid transition-[grid-template-columns] duration-300 ease-out" style="grid-template-columns: {cols}">
    <div class={cn('overflow-hidden', active === 'acquire' && 'pointer-events-none')}>
      <Button
        variant={active === 'preview' ? 'danger' : 'outline'}
        size="md"
        class={cn('w-full whitespace-nowrap', active === null && 'rounded-r-none')}
        disabled={!instrument || (active === null && !canPreview)}
        onclick={togglePreview}
      >
        {active === 'preview' ? 'Stop Preview' : 'Preview'}
      </Button>
    </div>
    <div class={cn('overflow-hidden', active === 'preview' && 'pointer-events-none')}>
      <Button
        variant={active === 'acquire' ? 'danger' : 'ghost'}
        size="md"
        class={cn(
          'w-full whitespace-nowrap',
          active === null &&
            'rounded-l-none border-l-0 border-border bg-success/15 text-success hover:bg-success/25 hover:text-success'
        )}
        disabled={!instrument || (active === null && !canAcquire)}
        onclick={toggleAcquire}
      >
        {active === 'acquire' ? 'Stop Acquisition' : 'Acquire'}
      </Button>
    </div>
  </div>
</div>

<AcquisitionDialog {app} bind:open={dialogOpen} />
