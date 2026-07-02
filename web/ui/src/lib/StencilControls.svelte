<script lang="ts">
  import type { Snippet } from 'svelte';

  import { Link, LinkOff } from '$lib/icons';
  import { Label, SpinBox } from '$lib/kit';
  import type { Instrument } from '$lib/model';
  import { cn, toastError } from '$lib/utils';

  interface Props {
    instrument: Instrument;
    class?: string;
  }

  let { instrument, class: className }: Props = $props();

  let offsetLinked = $state(false);
  let overlapLinked = $state(true);

  const stencil = $derived(instrument.state.stencil);
  const fovW = $derived(instrument.fov?.[0] ?? 0);
  const fovH = $derived(instrument.fov?.[1] ?? 0);
  const gridLimX = $derived((fovW * (1 - stencil.overlap_x)) / 1000);
  const gridLimY = $derived((fovH * (1 - stencil.overlap_y)) / 1000);
</script>

<section class={cn('flex flex-col gap-3', className)}>
  {#snippet offsetBody()}
    {#if offsetLinked}
      <SpinBox
        value={stencil.x_offset / 1000}
        min={-Math.min(gridLimX, gridLimY)}
        max={Math.min(gridLimX, gridLimY)}
        step={0.1}
        decimals={2}
        numCharacters={6}
        prefix="X / Y"
        suffix="mm"
        size="xs"
        align="right"
        onChange={(v) => toastError(instrument.updateStencil({ x_offset: v * 1000, y_offset: v * 1000 }))}
      />
    {:else}
      <SpinBox
        value={stencil.x_offset / 1000}
        min={-gridLimX}
        max={gridLimX}
        step={0.1}
        decimals={2}
        numCharacters={6}
        prefix="X"
        suffix="mm"
        size="xs"
        align="right"
        onChange={(v) => toastError(instrument.updateStencil({ x_offset: v * 1000 }))}
      />
      <SpinBox
        value={stencil.y_offset / 1000}
        min={-gridLimY}
        max={gridLimY}
        step={0.1}
        decimals={2}
        numCharacters={6}
        prefix="Y"
        suffix="mm"
        size="xs"
        align="right"
        onChange={(v) => toastError(instrument.updateStencil({ y_offset: v * 1000 }))}
      />
    {/if}
  {/snippet}
  {@render stencilRow(
    'Offset',
    offsetLinked,
    () => {
      offsetLinked = !offsetLinked;
      if (offsetLinked) toastError(instrument.updateStencil({ y_offset: stencil.x_offset }));
    },
    offsetBody
  )}

  {#snippet overlapBody()}
    {#if overlapLinked}
      <SpinBox
        value={stencil.overlap_x}
        min={0}
        max={0.5}
        step={0.01}
        decimals={3}
        numCharacters={6}
        prefix="X / Y"
        suffix="%"
        size="xs"
        align="right"
        onChange={(v) => toastError(instrument.updateStencil({ overlap_x: v, overlap_y: v }))}
      />
    {:else}
      <SpinBox
        value={stencil.overlap_x}
        min={0}
        max={0.5}
        step={0.01}
        decimals={3}
        numCharacters={6}
        prefix="X"
        suffix="%"
        size="xs"
        align="right"
        onChange={(v) => toastError(instrument.updateStencil({ overlap_x: v }))}
      />
      <SpinBox
        value={stencil.overlap_y}
        min={0}
        max={0.5}
        step={0.01}
        decimals={3}
        numCharacters={6}
        prefix="Y"
        suffix="%"
        size="xs"
        align="right"
        onChange={(v) => toastError(instrument.updateStencil({ overlap_y: v }))}
      />
    {/if}
  {/snippet}
  {@render stencilRow(
    'Overlap',
    overlapLinked,
    () => {
      overlapLinked = !overlapLinked;
      if (overlapLinked) toastError(instrument.updateStencil({ overlap_y: stencil.overlap_x }));
    },
    overlapBody
  )}

  <div class="flex flex-col gap-1 pb-2">
    <Label class="flex h-4 items-center">Default Z</Label>
    <div class="grid auto-cols-fr grid-flow-col items-center gap-1.5">
      <SpinBox
        value={stencil.z_start / 1000}
        step={0.001}
        decimals={3}
        numCharacters={8}
        prefix="Start"
        suffix="mm"
        size="xs"
        align="right"
        onChange={(v) => toastError(instrument.updateStencil({ z_start: v * 1000 }))}
      />
      <SpinBox
        value={stencil.z_end / 1000}
        step={0.001}
        decimals={3}
        numCharacters={8}
        prefix="End"
        suffix="mm"
        size="xs"
        align="right"
        onChange={(v) => toastError(instrument.updateStencil({ z_end: v * 1000 }))}
      />
    </div>
  </div>
</section>

{#snippet stencilRow(label: string, linked: boolean, onLink: () => void, body: Snippet)}
  <div class="flex flex-col gap-1">
    <div class="flex items-center justify-between gap-1">
      <Label>{label}</Label>
      <button
        class="flex h-4 w-4 items-center justify-center rounded text-fg-muted transition-colors hover:text-fg"
        title={linked ? 'Unlink X/Y' : 'Link X/Y'}
        onclick={onLink}
      >
        {#if linked}<Link class="h-3 w-3" />{:else}<LinkOff class="h-3 w-3" />{/if}
      </button>
    </div>
    <div class="grid auto-cols-fr grid-flow-col items-center gap-1.5">
      {@render body()}
    </div>
  </div>
{/snippet}
