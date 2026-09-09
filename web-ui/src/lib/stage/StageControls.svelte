<script lang="ts">
  import { Button } from '$lib/kit';
  import type { Stage } from '$lib/model';
  import { prefs } from '$lib/prefs';
  import { SpinBox } from '$lib/prop/numeric';
  import { fromMicrometers, getSpatialUnit, toMicrometers } from '$lib/spatial-units';
  import { cn, toastError } from '$lib/utils';

  interface Props {
    stage: Stage;
    class?: string;
  }

  let { stage, class: className }: Props = $props();
  const unit = $derived(getSpatialUnit(prefs.spatialUnit.get()));
  // Physical increments in µm, independent of the displayed unit.
  const AXIS_SPINS = [
    ['x', 10],
    ['y', 10],
    ['z', 1]
  ] as const;

  function axisModel(axis: 'x' | 'y' | 'z', step: number) {
    const selectedUnit = unit.value;
    return {
      value: fromMicrometers(stage.position(axis), selectedUnit),
      onChange: (value: number) => toastError(stage.axis(axis)?.move(toMicrometers(value, selectedUnit))),
      min: fromMicrometers(stage.axis(axis)?.lowerLimit?.value ?? 0, selectedUnit),
      max: fromMicrometers(stage.axis(axis)?.upperLimit?.value ?? 1, selectedUnit),
      step: fromMicrometers(step, selectedUnit)
    };
  }
</script>

<div class={cn('@container min-w-0', className)} role="group" aria-label="Stage movement controls">
  <div class="grid grid-cols-2 gap-2 @min-[40rem]:grid-cols-4">
    {#key unit.value}
      {#each AXIS_SPINS as [axis, step] (axis)}
        <SpinBox
          model={axisModel(axis, step)}
          decimals={unit.decimals}
          size="xs"
          align="right"
          prefix={axis.toUpperCase()}
          suffix={unit.label}
          class={cn('w-full min-w-0', stage.moving(axis) && 'text-danger')}
        />
      {/each}
    {/key}
    <Button
      variant={stage.anyMoving ? 'danger' : 'secondary'}
      size="xs"
      class="w-full min-w-0 disabled:opacity-100"
      onclick={() => toastError(stage.halt())}
      disabled={!stage.anyMoving}
      title="Halt stage motion"
    >
      Halt
    </Button>
  </div>
</div>
