<script lang="ts" module>
  import { tv } from 'tailwind-variants';

  // A switch is a small mark, so it is about 2/3 as tall as a box and 1.75 times as wide as it is tall. It has the
  // box line and fill, but it is round: in Voxel, a round part is a handle that slides, like a slider thumb. The gap
  // around the thumb is a part of the height, so each size has the same shape. On fills the track with blue, so
  // focus shows outside it, like on a blue Button.
  const switchStyles = tv({
    slots: {
      root: [
        'group inline-flex shrink-0 cursor-pointer items-center rounded-full [--switch-gap:calc(var(--switch-h)*0.15)]',
        'h-(--switch-h) w-[calc(var(--switch-h)*1.75)] p-(--switch-gap)',
        'data-[state=unchecked]:hover:bg-element-hover',
        'data-[state=checked]:bg-accent data-[state=checked]:ring-accent',
        'data-[state=checked]:focus-visible:outline-2 data-[state=checked]:focus-visible:outline-offset-2',
        'data-[state=checked]:focus-visible:outline-focus',
        'data-disabled:cursor-not-allowed data-disabled:opacity-50'
      ],
      thumb: [
        'pointer-events-none block size-[calc(var(--switch-h)-2*var(--switch-gap))] rounded-full',
        'transition-[translate,background-color] duration-150',
        'bg-fg-faint data-[state=unchecked]:group-hover:bg-fg-muted',
        'data-[state=checked]:translate-x-[calc(var(--switch-h)*0.75)] data-[state=checked]:bg-on-accent'
      ]
    },
    variants: {
      size: {
        sm: { root: '[--switch-h:calc(var(--ui-sm)*0.65)]' },
        md: { root: '[--switch-h:calc(var(--ui-md)*0.65)]' },
        lg: { root: '[--switch-h:calc(var(--ui-lg)*0.65)]' }
      }
    }
  });
</script>

<script lang="ts">
  import { Switch, type SwitchRootProps } from 'bits-ui';

  import { cn } from '../../utils/cn';
  import { box } from '../box';
  import type { BoolModel } from '../models.svelte';
  import { useValue, type ValueProps } from '../value.svelte';

  type Attributes = Omit<
    SwitchRootProps,
    'checked' | 'value' | 'disabled' | 'class' | 'style' | 'child' | 'children' | 'ref' | `on${string}`
  >;

  /** Turns something on or off right away, like a laser output. A click calls `onChange` at once. */
  type Props = ValueProps<boolean, BoolModel> &
    Attributes & {
      size?: 'sm' | 'md' | 'lg';
      disabled?: boolean;
      class?: string;
    };

  let { value, onChange, model, size = 'sm', disabled = false, class: className, ...attributes }: Props = $props();

  const control = useValue<boolean>(() => ({ value, onChange, model, disabled }));
  const styles = $derived(switchStyles({ size }));
</script>

<Switch.Root
  {...attributes}
  bind:checked={() => control.value, (on) => void control.change(on)}
  disabled={control.disabled}
  class={cn(box({ hover: false }), styles.root({ class: className }))}
>
  <Switch.Thumb class={styles.thumb()} />
</Switch.Root>
