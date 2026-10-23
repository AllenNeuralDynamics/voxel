<script lang="ts" module>
  import { tv } from 'tailwind-variants';

  const checkboxStyles = tv({
    base: [
      'flex items-center justify-center rounded border',
      'border-control-line bg-element-bg',
      'transition-colors',
      'disabled:cursor-not-allowed disabled:opacity-50',
      'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus',
      'data-[state=checked]:border-accent data-[state=checked]:bg-accent',
      'data-[state=indeterminate]:border-accent data-[state=indeterminate]:bg-accent'
    ],
    variants: {
      size: {
        sm: 'size-3 ',
        md: 'size-3.5 ',
        lg: 'size-4 '
      }
    }
  });

  const iconSizes = { sm: 8, md: 10, lg: 12 } as const;
</script>

<script lang="ts">
  import { Checkbox, type CheckboxRootProps } from 'bits-ui';

  import type { BoolModel } from '$lib/core/model/prop.svelte';
  import { Check, Minus } from '$lib/kit/icons';

  import { useValue, type ValueProps } from '../value.svelte';

  type Attributes = Omit<
    CheckboxRootProps,
    | 'checked'
    | 'indeterminate'
    | 'value'
    | 'disabled'
    | 'class'
    | 'style'
    | 'child'
    | 'children'
    | 'ref'
    | `on${string}`
  >;

  /** Picks or includes something, or sets a form option. A click calls `onChange` at once. */
  type Props = ValueProps<boolean, BoolModel> &
    Attributes & {
      /** Shows the mixed mark, for a group where only some items are checked. A click sends true. */
      indeterminate?: boolean;
      size?: 'sm' | 'md' | 'lg';
      disabled?: boolean;
      class?: string;
    };

  let {
    value,
    onChange,
    model,
    indeterminate = false,
    size = 'md',
    disabled = false,
    class: className,
    ...attributes
  }: Props = $props();

  const control = useValue<boolean>(() => ({ value, onChange, model, disabled }));
</script>

<!-- The page decides when the box stops being mixed, so the box ignores its own change to it. -->
<Checkbox.Root
  {...attributes}
  bind:checked={() => control.value, (on) => void control.change(on)}
  bind:indeterminate={() => indeterminate, () => {}}
  disabled={control.disabled}
  class={checkboxStyles({ size, class: className })}
>
  {#if control.value}
    <Check class="text-on-accent" width={iconSizes[size]} height={iconSizes[size]} />
  {:else if indeterminate}
    <Minus class="text-on-accent" width={iconSizes[size]} height={iconSizes[size]} />
  {/if}
</Checkbox.Root>
