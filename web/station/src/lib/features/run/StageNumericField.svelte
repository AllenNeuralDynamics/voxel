<script module lang="ts">
  import type { SpatialUnit } from '$lib/core/prefs';

  /** `scale` is µm per shown unit; values stay in µm. `step` and `bigStep` are in the shown unit. */
  export interface UnitSteps {
    label: string;
    scale: number;
    step: number;
    bigStep: number;
    decimals: number;
  }

  export const SPATIAL_UNITS: Record<SpatialUnit, UnitSteps> = {
    mm: { label: 'mm', scale: 1000, step: 0.001, bigStep: 0.1, decimals: 3 },
    um: { label: 'µm', scale: 1, step: 1, bigStep: 100, decimals: 1 }
  };
</script>

<script lang="ts">
  import { Button, NumberBox } from '@voxel/kit';
  import { Crosshair } from '@voxel/kit/icons';

  interface Props {
    /** Where the stage is on this field's axis, in µm. */
    position: number | undefined;
    unit: UnitSteps;
    value: number | null | undefined;
    onChange: (value: number) => unknown;
    onEditStart?: () => () => void;
    min?: number | null;
    max?: number | null;
    prefix?: string;
    disabled?: boolean;
    'aria-label'?: string;
  }

  let { position, unit, value, onChange, disabled = false, ...fieldProps }: Props = $props();

  function useStagePosition() {
    if (disabled || position === undefined || Object.is(value, position)) return;
    onChange(position);
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
    disabled={disabled || position === undefined}
    aria-label="Use the stage position"
    title="Use the stage position"
    onclick={useStagePosition}
  >
    <Crosshair class="size-3.5" />
  </Button>
</NumberBox>
