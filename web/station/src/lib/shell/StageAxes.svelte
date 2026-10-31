<script lang="ts">
  import type { Stage } from '$lib/core/model';
  import { prefs } from '$lib/core/prefs';
  import { fromMicrometers, getSpatialUnit, toMicrometers } from '$lib/core/spatial-units';
  import { Button, SpinBox } from '@voxel/kit';
  import { cn } from '@voxel/kit/cn';
  import { reportFailure } from '@voxel/kit/failures';

  interface Props {
    stage: Stage;
  }

  let { stage }: Props = $props();

  const unit = $derived(getSpatialUnit(prefs.spatialUnit.get()));
  // The step of each stage axis box, in µm, whatever unit shows.
  const AXIS_SPINS = [
    ['x', 10],
    ['y', 10],
    ['z', 1]
  ] as const;
</script>

<div
  class="grid min-w-0 grid-cols-4 gap-2 @min-[64rem]/viewer-pane:grid-cols-[repeat(3,10rem)_auto]"
  role="group"
  aria-label="Stage movement controls"
>
  {#each AXIS_SPINS as [axis, step] (axis)}
    <SpinBox
      value={fromMicrometers(stage.position(axis), unit.value)}
      onChange={(value) => reportFailure(stage.axis(axis)?.move(toMicrometers(value, unit.value)))}
      min={fromMicrometers(stage.axis(axis)?.lowerLimit?.value ?? 0, unit.value)}
      max={fromMicrometers(stage.axis(axis)?.upperLimit?.value ?? 1, unit.value)}
      step={fromMicrometers(step, unit.value)}
      decimals={unit.decimals}
      prefix={axis.toUpperCase()}
      suffix={unit.label}
      class={cn('w-full min-w-0', stage.moving(axis) && 'animate-pulse text-fg-muted')}
    />
  {/each}
  <Button
    variant={stage.anyMoving ? 'danger' : 'secondary'}
    class="w-full min-w-14 disabled:opacity-100"
    onclick={() => reportFailure(stage.halt())}
    disabled={!stage.anyMoving}
    title="Halt stage motion"
  >
    Halt
  </Button>
</div>
