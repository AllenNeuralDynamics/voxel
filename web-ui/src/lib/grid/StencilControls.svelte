<script lang="ts">
  import { Link, LinkOff } from '$lib/icons';
  import type { Instrument } from '$lib/model';
  import { prefs } from '$lib/prefs';
  import { SpinBox } from '$lib/prop/numeric';
  import { getSpatialUnit } from '$lib/spatial-units';
  import { cn, toastError } from '$lib/utils';

  interface Props {
    instrument: Instrument;
    class?: string;
  }

  let { instrument, class: className }: Props = $props();

  let offsetLinked = $state(false);
  let overlapLinked = $state(true);

  const unit = $derived(getSpatialUnit(prefs.spatialUnit.get()));
  const stencil = $derived(instrument.state.stencil);
  const fovW = $derived(instrument.fov?.[0] ?? 0);
  const fovH = $derived(instrument.fov?.[1] ?? 0);
  const gridLimX = $derived((fovW * (1 - stencil.overlap_x)) / unit.scale);
  const gridLimY = $derived((fovH * (1 - stencil.overlap_y)) / unit.scale);
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

{#key unit.value}
  <div class={cn('flex flex-col gap-6', className)}>
    <!-- Offset -->
    <div class="flex flex-col gap-2">
      <div class="flex items-center justify-between">
        <span class=" text-fg-muted">Offset</span>
        {@render linkButton(offsetLinked, () => {
          offsetLinked = !offsetLinked;
          if (offsetLinked) toastError(instrument.updateStencil({ y_offset: stencil.x_offset }));
        })}
      </div>
      {#if offsetLinked}
        <SpinBox
          model={{
            value: stencil.x_offset / unit.scale,
            onChange: (v) =>
              toastError(instrument.updateStencil({ x_offset: v * unit.scale, y_offset: v * unit.scale })),
            min: -Math.min(gridLimX, gridLimY),
            max: Math.min(gridLimX, gridLimY),
            step: 10 / unit.scale,
            home: 0
          }}
          decimals={unit.decimals}
          numCharacters={5}
          prefix="X/Y"
          suffix={unit.label}
          size="xs"
          align="right"
        />
      {:else}
        <SpinBox
          model={{
            value: stencil.x_offset / unit.scale,
            onChange: (v) => toastError(instrument.updateStencil({ x_offset: v * unit.scale })),
            min: -gridLimX,
            max: gridLimX,
            step: 10 / unit.scale,
            home: 0
          }}
          decimals={unit.decimals}
          numCharacters={5}
          prefix="X"
          suffix={unit.label}
          size="xs"
          align="right"
        />
        <SpinBox
          model={{
            value: stencil.y_offset / unit.scale,
            onChange: (v) => toastError(instrument.updateStencil({ y_offset: v * unit.scale })),
            min: -gridLimY,
            max: gridLimY,
            step: 10 / unit.scale,
            home: 0
          }}
          decimals={unit.decimals}
          numCharacters={5}
          prefix="Y"
          suffix={unit.label}
          size="xs"
          align="right"
        />
      {/if}
    </div>

    <!-- Overlap -->
    <div class="flex flex-col gap-2">
      <div class="flex items-center justify-between">
        <span class=" text-fg-muted">Overlap</span>
        {@render linkButton(overlapLinked, () => {
          overlapLinked = !overlapLinked;
          if (overlapLinked) toastError(instrument.updateStencil({ overlap_y: stencil.overlap_x }));
        })}
      </div>
      {#if overlapLinked}
        <SpinBox
          model={{
            value: stencil.overlap_x,
            onChange: (v) => toastError(instrument.updateStencil({ overlap_x: v, overlap_y: v })),
            min: 0,
            max: 0.5,
            step: 0.01,
            home: 0.15
          }}
          decimals={3}
          numCharacters={5}
          prefix="X/Y"
          suffix="%"
          size="xs"
          align="right"
        />
      {:else}
        <SpinBox
          model={{
            value: stencil.overlap_x,
            onChange: (v) => toastError(instrument.updateStencil({ overlap_x: v })),
            min: 0,
            max: 0.5,
            step: 0.01,
            home: 0.15
          }}
          decimals={3}
          numCharacters={5}
          prefix="X"
          suffix="%"
          size="xs"
          align="right"
        />
        <SpinBox
          model={{
            value: stencil.overlap_y,
            onChange: (v) => toastError(instrument.updateStencil({ overlap_y: v })),
            min: 0,
            max: 0.5,
            step: 0.01,
            home: 0.15
          }}
          decimals={3}
          numCharacters={5}
          prefix="Y"
          suffix="%"
          size="xs"
          align="right"
        />
      {/if}
    </div>

    <!-- Z range -->
    <div class="flex flex-col gap-2">
      <span class=" text-fg-muted">Z range</span>
      <SpinBox
        model={{
          value: stencil.z_start / unit.scale,
          onChange: (v) => toastError(instrument.updateStencil({ z_start: v * unit.scale })),
          step: 1 / unit.scale
        }}
        decimals={unit.decimals}
        numCharacters={6}
        prefix="Start"
        suffix={unit.label}
        size="xs"
        align="right"
      />
      <SpinBox
        model={{
          value: stencil.z_end / unit.scale,
          onChange: (v) => toastError(instrument.updateStencil({ z_end: v * unit.scale })),
          step: 1 / unit.scale
        }}
        decimals={unit.decimals}
        numCharacters={6}
        prefix="End"
        suffix={unit.label}
        size="xs"
        align="right"
      />
    </div>
  </div>
{/key}
