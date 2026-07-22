<script lang="ts" module>
  import { tv, type VariantProps } from 'tailwind-variants';

  export const buttonVariants = tv({
    base: [
      'inline-flex shrink-0 items-center justify-center',
      'rounded border font-medium',
      'transition-[color,background-color,border-color,transform] focus:outline-none',
      'focus-visible:ring-2 focus-visible:ring-focused focus-visible:ring-offset-2 focus-visible:ring-offset-canvas',
      'active:scale-[0.98]',
      'disabled:pointer-events-none disabled:opacity-80',
      '[&_svg]:pointer-events-none [&_svg]:shrink-0'
    ],
    variants: {
      variant: {
        default: 'border-primary bg-primary text-primary-fg hover:bg-primary/90 active:bg-primary/80',
        secondary:
          'border-input bg-element-bg text-fg hover:border-border hover:bg-element-hover active:bg-element-active',
        outline:
          'border-input bg-transparent hover:border-border hover:bg-element-hover hover:text-fg active:bg-element-active focus:border-focused',
        ghost: 'border-transparent hover:bg-element-hover hover:text-fg active:bg-element-active focus:border-focused',
        danger: 'border-danger bg-danger text-danger-fg hover:bg-danger/90 active:bg-danger/80',
        success: 'border-success bg-success text-success-fg hover:bg-success/90 active:bg-success/80',
        link: 'border-transparent text-primary underline-offset-4 hover:underline active:text-primary/70'
      },
      size: {
        xs: 'h-ui-xs gap-1 px-1.5 text-base',
        sm: 'h-ui-sm gap-1.5 px-2 text-lg',
        md: 'h-ui-md gap-1.5 px-3 text-xl',
        lg: 'h-ui-lg gap-2 px-3 text-xl capitalize',
        'icon-xs': 'size-ui-xs',
        icon: 'size-ui-sm',
        'icon-lg': 'size-ui-md'
      }
    },
    defaultVariants: {
      variant: 'default',
      size: 'md'
    }
  });

  export type ButtonVariants = VariantProps<typeof buttonVariants>;
</script>

<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { HTMLButtonAttributes } from 'svelte/elements';

  interface Props extends HTMLButtonAttributes, ButtonVariants {
    class?: string;
    children?: Snippet;
  }

  let { variant = 'default', size = 'md', class: className = '', children, ...restProps }: Props = $props();
</script>

<button class={buttonVariants({ variant, size, class: className })} {...restProps}>
  {#if children}{@render children()}{/if}
</button>
