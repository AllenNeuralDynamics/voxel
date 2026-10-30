<script lang="ts" module>
  import { tv } from 'tailwind-variants';

  // The box is the track, and the picked option sits on a lighter pill in it. The pill corner is the box corner
  // minus the gap around the pill. In a row, the options share the width. In a column, they share the width of the
  // widest option.
  const radioBarStyles = tv({
    slots: {
      root: 'inline-grid min-w-0 p-0.5',
      option: [
        'flex min-w-0 items-center justify-center rounded-[0.125rem] text-fg-muted outline-none',
        'enabled:cursor-pointer enabled:hover:text-fg',
        'data-[state=checked]:bg-element-selected enabled:data-[state=checked]:text-fg'
      ]
    },
    variants: {
      orientation: {
        horizontal: { root: 'auto-cols-fr grid-flow-col' },
        vertical: { root: 'grid-flow-row auto-rows-fr' }
      },
      size: {
        // 4 steps below the base, 2 below sm, with smaller text. Only the RadioBar has it, so it does not line up
        // with other boxes. It suits a compact row, such as a card header next to a small switch.
        xs: { root: 'text-sm', option: 'px-1.5' },
        sm: { option: 'px-2' },
        md: { option: 'px-2' },
        lg: { option: 'px-2.5' }
      }
    },
    compoundVariants: [
      // In a row, the bar has the box height, and the options fill it.
      { orientation: 'horizontal', size: 'xs', class: { root: 'h-ui-xs' } },
      { orientation: 'horizontal', size: 'sm', class: { root: 'h-ui-sm' } },
      { orientation: 'horizontal', size: 'md', class: { root: 'h-ui-md' } },
      { orientation: 'horizontal', size: 'lg', class: { root: 'h-ui-lg' } },
      // In a column, each option is as high as an option in a row: the box height less the gap around the pill.
      { orientation: 'vertical', size: 'xs', class: { option: 'h-[calc(var(--ui-xs)-0.25rem)]' } },
      { orientation: 'vertical', size: 'sm', class: { option: 'h-[calc(var(--ui-sm)-0.25rem)]' } },
      { orientation: 'vertical', size: 'md', class: { option: 'h-[calc(var(--ui-md)-0.25rem)]' } },
      { orientation: 'vertical', size: 'lg', class: { option: 'h-[calc(var(--ui-lg)-0.25rem)]' } }
    ]
  });
</script>

<script lang="ts" generics="T extends string | number">
  import { RadioGroup, type RadioGroupRootProps } from 'bits-ui';

  import { cn } from '$lib/core/utils';

  import { box } from '../box';
  import { type EnumeratedProps, optionKey, useEnumerated } from './enumerated.svelte';

  type Attributes = Omit<
    RadioGroupRootProps,
    'child' | 'children' | 'class' | 'disabled' | 'orientation' | 'ref' | 'style' | 'value' | `on${string}`
  >;

  /** Picks 1 of 2 to 4 short options. All options show, and 1 click picks. Use a Select for a longer list. */
  type Props = EnumeratedProps<T> &
    Attributes & {
      /** The text of an option. By default, the option shows as it is. */
      formatLabel?: (option: T) => string;
      disabled?: boolean;
      /** `xs` is lower than the other boxes, for a compact row. */
      size?: 'xs' | 'sm' | 'md' | 'lg';
      /** `vertical` stacks the options in a column. Each option keeps the height it has in a row. */
      orientation?: 'horizontal' | 'vertical';
      class?: string;
    };

  let {
    value,
    options,
    onChange,
    model,
    formatLabel = String,
    disabled = false,
    size = 'sm',
    orientation = 'horizontal',
    class: className,
    ...attributes
  }: Props = $props();

  const control = useEnumerated<T>(() => ({ value, options, onChange, model, disabled }));
  const styles = $derived(radioBarStyles({ size, orientation }));
</script>

<RadioGroup.Root
  {...attributes}
  bind:value={() => optionKey(control.value), (key) => control.pick(key)}
  {orientation}
  disabled={control.disabled}
  class={styles.root({
    // The shared box has no xs size, so an xs bar takes its text size from its own styles.
    class: cn(
      box({ size: size === 'xs' ? undefined : size, state: control.disabled ? 'locked' : 'idle', hover: false }),
      className
    )
  })}
>
  {#each control.options as option (option)}
    <RadioGroup.Item value={optionKey(option)} class={styles.option()}>
      <span class="truncate">{formatLabel(option)}</span>
    </RadioGroup.Item>
  {/each}
</RadioGroup.Root>
