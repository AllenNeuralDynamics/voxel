<script lang="ts" generics="Clearable extends boolean = false">
  import { type BoxProps, type RangeProps, useNumberModel } from './number.svelte';
  import NumberBox from './NumberBox.svelte';
  import Slider from './Slider.svelte';

  /** A number in the box, with a slider at its right end. The slider is for the mouse; the keys use the number. */
  type Props = RangeProps<Clearable> & BoxProps;

  let {
    value,
    onChange,
    model: given,
    clearable,
    min,
    max,
    step,
    bigStep,
    home,
    onEditStart,
    disabled = false,
    ref = $bindable(null),
    ...rest
  }: Props = $props();

  const model = useNumberModel(() => ({
    value,
    onChange,
    model: given,
    clearable,
    min,
    max,
    step,
    bigStep,
    home,
    onEditStart,
    disabled
  }));
</script>

<NumberBox bind:ref {model} {disabled} grow={false} {...rest}>
  <!-- The slider lies inside the box, so it drops its own line, fill and corners, and it takes the box height. -->
  <Slider
    {model}
    {disabled}
    variant="bar"
    tabindex={-1}
    aria-hidden="true"
    class="h-full! flex-1 rounded-none bg-transparent p-0 ring-0"
  />
</NumberBox>
