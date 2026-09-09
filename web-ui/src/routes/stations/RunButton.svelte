<script lang="ts">
  import { watch } from 'runed';

  import AcquisitionDialog from '$lib/AcquisitionDialog.svelte';
  import { Button } from '$lib/kit';
  import type { Station } from '$lib/model';
  import { getPreviewContext } from '$lib/preview/session.svelte';
  import { cn, toastError } from '$lib/utils';

  interface Props {
    app: Station;
    class?: string;
  }

  let { app, class: className }: Props = $props();

  const previews = getPreviewContext();
  const instrument = $derived(app.instrument);
  const preview = $derived(previews.current);
  const canPreview = $derived(preview?.channels.some((channel) => channel.visible) ?? false);

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
    if (!instrument || !preview) return;
    if (active === 'preview') {
      setOptimistic(null);
      preview.stopPreview();
    } else {
      setOptimistic('preview');
      preview.startPreview();
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

<div class={cn('flex items-center gap-2', className)}>
  <div class="w-full">
    <div class="grid transition-[grid-template-columns] duration-300 ease-out" style="grid-template-columns: {cols}">
      <div class={cn('overflow-hidden', active === 'acquire' && 'pointer-events-none')}>
        <Button
          variant={active === 'preview' ? 'danger' : 'secondary'}
          size="md"
          class={cn('w-full whitespace-nowrap', active === null && 'rounded-r-none border-border')}
          disabled={!instrument || (active === null && !canPreview)}
          onclick={togglePreview}
        >
          {active === 'preview' ? 'Stop Preview' : 'Preview'}
        </Button>
      </div>
      <div class={cn('overflow-hidden', active === 'preview' && 'pointer-events-none')}>
        <Button
          variant={active === 'acquire' ? 'danger' : 'secondary'}
          size="md"
          class={cn('w-full whitespace-nowrap', active === null && 'rounded-l-none border-l-0 border-border')}
          disabled={!instrument}
          onclick={toggleAcquire}
        >
          {active === 'acquire' ? 'Stop Acquisition' : 'Acquire'}
        </Button>
      </div>
    </div>
  </div>
</div>

<AcquisitionDialog {app} bind:open={dialogOpen} />
