<script lang="ts" module>
  import { tv, type VariantProps } from 'tailwind-variants';

  export const switchVariants = tv({
    slots: {
      root: [
        'group flex cursor-pointer items-center rounded-full transition-colors',
        'border border-fg-faint data-[state=checked]:border-primary-soft',
        'bg-element-bg hover:bg-element-hover',
        'data-[state=checked]:bg-primary-soft data-[state=checked]:hover:bg-primary-soft',
        'data-disabled:cursor-not-allowed data-disabled:opacity-40',
        'h-[var(--switch-h)] w-[calc(var(--switch-h)*1.8)] px-[calc(var(--switch-h)*0.1)]'
      ],
      thumb: [
        'block rounded-full transition-[margin-left,colors]',
        'bg-zinc-400 group-hover:bg-zinc-200 data-[state=checked]:bg-zinc-100',
        'h-[calc(var(--switch-h)*0.7)] w-[calc(var(--switch-h)*0.7)]',
        'ml-0 data-[state=checked]:ml-[calc(var(--switch-h)*0.8)]'
      ]
    },
    variants: {
      size: {
        xs: { root: '[--switch-h:calc(var(--ui-xs)*0.65)]' },
        sm: { root: '[--switch-h:calc(var(--ui-sm)*0.65)]' },
        md: { root: '[--switch-h:calc(var(--ui-md)*0.65)]' },
        lg: { root: '[--switch-h:calc(var(--ui-lg)*0.65)]' }
      }
    },
    defaultVariants: {
      size: 'md'
    }
  });

  export type SwitchVariants = VariantProps<typeof switchVariants>;
</script>

<script lang="ts">
  import { Switch as SwitchPrimitive } from 'bits-ui';

  interface Props extends SwitchVariants {
    checked?: boolean;
    onCheckedChange?: (checked: boolean) => void;
    disabled?: boolean;
    style?: string;
    class?: string;
  }

  let {
    checked = $bindable(false),
    onCheckedChange,
    disabled = false,
    size = 'md',
    style,
    class: className = ''
  }: Props = $props();

  const styles = $derived(switchVariants({ size }));
</script>

<SwitchPrimitive.Root bind:checked {onCheckedChange} {disabled} {style} class={styles.root({ class: className })}>
  <SwitchPrimitive.Thumb class={styles.thumb()} />
</SwitchPrimitive.Root>
