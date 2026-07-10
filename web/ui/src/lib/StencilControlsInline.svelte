<script lang="ts">
  import { Link, LinkOff } from '$lib/icons';
  import { SpinBox } from '$lib/kit';
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

{#snippet linkButton(linked: boolean, onLink: () => void)}
  <button
    class="flex h-4 w-4 shrink-0 items-center justify-center rounded text-fg-muted transition-colors hover:text-fg"
    title={linked ? 'Unlink X/Y' : 'Link X/Y'}
    onclick={onLink}
  >
    {#if linked}<Link class="h-3 w-3" />{:else}<LinkOff class="h-3 w-3" />{/if}
  </button>
{/snippet}

<div class={cn('flex flex-col gap-6', className)}>
  <!-- Offset -->
  <div class="flex flex-col gap-2">
    <div class="flex items-center justify-between">
      <span class="text-xs text-fg-muted">Offset</span>
      {@render linkButton(offsetLinked, () => {
        offsetLinked = !offsetLinked;
        if (offsetLinked) toastError(instrument.updateStencil({ y_offset: stencil.x_offset }));
      })}
    </div>
    {#if offsetLinked}
      <SpinBox
        value={stencil.x_offset / 1000}
        min={-Math.min(gridLimX, gridLimY)}
        max={Math.min(gridLimX, gridLimY)}
        step={0.1}
        decimals={2}
        numCharacters={5}
        prefix="X/Y"
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
        numCharacters={5}
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
        numCharacters={5}
        prefix="Y"
        suffix="mm"
        size="xs"
        align="right"
        onChange={(v) => toastError(instrument.updateStencil({ y_offset: v * 1000 }))}
      />
    {/if}
  </div>

  <!-- Overlap -->
  <div class="flex flex-col gap-2">
    <div class="flex items-center justify-between">
      <span class="text-xs text-fg-muted">Overlap</span>
      {@render linkButton(overlapLinked, () => {
        overlapLinked = !overlapLinked;
        if (overlapLinked) toastError(instrument.updateStencil({ overlap_y: stencil.overlap_x }));
      })}
    </div>
    {#if overlapLinked}
      <SpinBox
        value={stencil.overlap_x}
        min={0}
        max={0.5}
        step={0.01}
        decimals={3}
        numCharacters={5}
        prefix="X/Y"
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
        numCharacters={5}
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
        numCharacters={5}
        prefix="Y"
        suffix="%"
        size="xs"
        align="right"
        onChange={(v) => toastError(instrument.updateStencil({ overlap_y: v }))}
      />
    {/if}
  </div>

  <!-- Z range -->
  <div class="flex flex-col gap-2">
    <span class="text-xs text-fg-muted">Z range</span>
    <SpinBox
      value={stencil.z_start / 1000}
      step={0.001}
      decimals={3}
      numCharacters={6}
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
      numCharacters={6}
      prefix="End"
      suffix="mm"
      size="xs"
      align="right"
      onChange={(v) => toastError(instrument.updateStencil({ z_end: v * 1000 }))}
    />
  </div>
</div>
