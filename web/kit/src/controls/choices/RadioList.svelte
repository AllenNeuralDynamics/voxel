<script lang="ts" module>
  import { tv } from 'tailwind-variants';

  // The dot has the Checkbox's box and colors, round; the picked one is filled with the accent and shows a small
  // center dot.
  const radioListStyles = tv({
    slots: {
      root: 'flex min-w-0 flex-col gap-1',
      option: [
        'group flex min-w-0 items-center gap-2 rounded-sm text-left outline-none',
        'enabled:cursor-pointer disabled:cursor-not-allowed disabled:opacity-50'
      ],
      dot: [
        'flex shrink-0 items-center justify-center rounded-full border border-control-line bg-element-bg transition-colors',
        'group-focus-visible:outline-2 group-focus-visible:outline-offset-2 group-focus-visible:outline-focus',
        'group-data-[state=checked]:border-accent group-data-[state=checked]:bg-accent'
      ],
      center: 'rounded-full bg-on-accent'
    },
    variants: {
      size: {
        sm: { option: 'min-h-ui-xs', dot: 'size-3', center: 'size-1' },
        md: { option: 'min-h-ui-sm', dot: 'size-3.5', center: 'size-1.5' },
        lg: { option: 'min-h-ui-md text-lg', dot: 'size-4', center: 'size-1.5' }
      }
    }
  });
</script>

<script lang="ts" generics="T extends string | number">
  import { RadioGroup, type RadioGroupRootProps } from 'bits-ui';

  import { type EnumeratedProps, optionKey, useEnumerated } from './enumerated.svelte';

  type Attributes = Omit<
    RadioGroupRootProps,
    'child' | 'children' | 'class' | 'disabled' | 'orientation' | 'ref' | 'style' | 'value' | `on${string}`
  >;

  /**
   * Picks 1 option from a short list, each on its own row with a round mark and its text. It takes more room than a
   * RadioBar and holds longer text; use a Select for a long list.
   */
  type Props = EnumeratedProps<T> &
    Attributes & {
      /** The text of an option. By default, the option shows as it is. */
      display?: (option: T) => string;
      disabled?: boolean;
      size?: 'sm' | 'md' | 'lg';
      class?: string;
    };

  let {
    value,
    options,
    onChange,
    model,
    display = String,
    disabled = false,
    size = 'md',
    class: className,
    ...attributes
  }: Props = $props();

  const control = useEnumerated<T>(() => ({ value, options, onChange, model, disabled }));
  const styles = $derived(radioListStyles({ size }));
</script>

<RadioGroup.Root
  {...attributes}
  bind:value={() => optionKey(control.value), (key) => control.pick(key)}
  disabled={control.disabled}
  class={styles.root({ class: className })}
>
  {#each control.options as option (option)}
    <RadioGroup.Item value={optionKey(option)} class={styles.option()}>
      {#snippet children({ checked })}
        <span class={styles.dot()}
          >{#if checked}<span class={styles.center()}></span>{/if}</span
        >
        <span class="min-w-0 truncate">{display(option)}</span>
      {/snippet}
    </RadioGroup.Item>
  {/each}
</RadioGroup.Root>
