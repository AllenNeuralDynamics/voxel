<script lang="ts" module>
  import { tv, type VariantProps } from 'tailwind-variants';

  export const switchVariants = tv({
    slots: {
      root: [
        'group flex cursor-pointer items-center rounded-full transition-colors',
        'border border-border data-[state=checked]:border-primary',
        'bg-element-bg/30 hover:bg-element-hover/60',
        'data-[state=checked]:bg-primary/90 data-[state=checked]:hover:bg-primary',
        'data-disabled:cursor-not-allowed data-disabled:opacity-40',
        'h-[var(--switch-h)] w-[calc(var(--switch-h)*1.8)] px-[calc(var(--switch-h)*0.1)]'
      ],
      thumb: [
        'block rounded-full transition-[margin-left,colors]',
        'bg-fg-faint/50 group-hover:bg-fg-faint data-[state=checked]:bg-fg-muted',
        'h-[calc(var(--switch-h)*0.7)] w-[calc(var(--switch-h)*0.7)]',
        'ml-0 data-[state=checked]:ml-[calc(var(--switch-h)*0.8)]'
      ]
    },
    variants: {
      size: {
        xs: { root: '[--switch-h:calc(var(--ui-xs)*0.95)]' },
        sm: { root: '[--switch-h:calc(var(--ui-sm)*0.95)]' },
        md: { root: '[--switch-h:calc(var(--ui-md)*0.95)]' },
        lg: { root: '[--switch-h:calc(var(--ui-lg)*0.95)]' }
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
