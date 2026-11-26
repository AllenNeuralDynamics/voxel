<script lang="ts">
  import type { SpecimenAxis } from '$lib/core/types';
  import type { UnitSteps } from '$lib/features/run/StageNumericField.svelte';
  import { NumberBox } from '@voxel/kit';

  interface Props {
    /** The strip's axis: its box starts at the strip's edge and takes the strip's letter. */
    third: SpecimenAxis;
    /** The map's 2 axes, each with its letter beside its box. */
    plane: [SpecimenAxis, SpecimenAxis];
    position: Partial<Record<SpecimenAxis, number>>;
    unit: UnitSteps;
    /** Room to leave at the right, in px, for the scale bar. */
    right: number;
    disabled?: boolean;
    onmove?: (axis: SpecimenAxis, value: number) => void;
  }

  let { third, plane, position, unit, right, disabled = false, onmove }: Props = $props();

  const BOX = 'pointer-events-auto w-[6.2rem] flex-none bg-raised text-sm hover:bg-raised';
</script>

{#snippet field(axis: SpecimenAxis, edge: boolean)}
  <NumberBox
    size="sm"
    class={[BOX, edge && 'rounded-l-none'].filter(Boolean).join(' ')}
    value={position[axis]}
    step={unit.step * unit.scale}
    bigStep={unit.bigStep * unit.scale}
    displayScale={unit.scale}
    decimals={unit.decimals}
    align="right"
    aria-label="{axis.toUpperCase()} position, {unit.label}"
    disabled={disabled || position[axis] === undefined}
    onChange={(value) => onmove?.(axis, value)}
  />
{/snippet}

<section
  aria-label="Stage position"
  class="pointer-events-none absolute bottom-4 left-0 z-10 flex items-end gap-2"
  style:right="{right}px"
>
  {@render field(third, true)}
  <span class="flex min-w-0 flex-auto flex-wrap-reverse gap-2">
    {#each plane as axis (axis)}
      <span class="flex flex-none items-center gap-2">
        <span class="ml-1.5 flex-none font-mono text-sm font-medium" style:color="var(--axis-{axis})">
          {axis.toUpperCase()}
        </span>
        {@render field(axis, false)}
      </span>
    {/each}
  </span>
</section>
