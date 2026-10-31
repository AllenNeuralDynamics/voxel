<script lang="ts">
  import type { EditContext, Stage } from '$lib/core/model';
  import type { SpatialUnitDefinition } from '$lib/core/spatial-units';
  import { Button, NumberBox } from '@voxel/kit';
  import { Crosshair } from '@voxel/kit/icons';

  interface Props {
    stage?: Stage | null;
    axis: 'x' | 'y' | 'z';
    unit: SpatialUnitDefinition;
    value: number | null | undefined;
    onChange: (value: number, edit: EditContext) => unknown;
    onEditStart?: () => () => void;
    min?: number | null;
    max?: number | null;
    prefix?: string;
    disabled?: boolean;
  }

  let { stage, axis, unit, value, onChange, disabled = false, ...fieldProps }: Props = $props();

  const position = $derived(stage?.axis(axis).position?.value ?? null);

  function useStagePosition() {
    if (disabled || position == null || Object.is(value, position)) return;
    onChange(position, {});
  }
</script>

<NumberBox
  {value}
  {onChange}
  suffix={unit.label}
  step={unit.step * unit.scale}
  bigStep={unit.bigStep * unit.scale}
  displayScale={unit.scale}
  decimals={unit.decimals}
  {disabled}
  {...fieldProps}
>
  <Button
    variant="ghost"
    size="icon-sm"
    class="h-full rounded-none border-0 text-fg-muted focus-visible:ring-offset-0 focus-visible:ring-inset"
    disabled={disabled || position == null}
    aria-label="Use current stage position"
    title="Use current stage position"
    onclick={useStagePosition}
  >
    <Crosshair class="size-3.5" />
  </Button>
</NumberBox>
