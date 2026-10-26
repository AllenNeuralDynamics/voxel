<script lang="ts" module>
  import { tv, type VariantProps } from 'tailwind-variants';

  export const buttonVariants = tv({
    base: [
      'inline-flex shrink-0 items-center justify-center',
      'rounded-sm border font-medium',
      'transition-[color,background-color,border-color,transform] focus:outline-none',
      'focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-canvas',
      'active:scale-[0.98]',
      'disabled:pointer-events-none disabled:opacity-80',
      '[&_svg]:pointer-events-none [&_svg]:shrink-0'
    ],
    variants: {
      variant: {
        default: 'border-accent bg-accent text-on-accent hover:bg-accent-hover active:bg-accent-hover',
        secondary:
          'border-control-line bg-element-bg text-fg hover:border-control-line-hover hover:bg-element-hover active:bg-element-active',
        outline:
          'border-control-line bg-transparent hover:border-control-line-hover hover:bg-element-hover hover:text-fg active:bg-element-active focus-visible:border-focus',
        // A dashed edge marks the place of an item to come, such as a button that adds to a list.
        dashed:
          'border-dashed border-control-line bg-transparent text-fg-muted hover:border-control-line-hover hover:bg-element-hover hover:text-fg active:bg-element-active focus-visible:border-focus',
        ghost:
          'border-transparent hover:bg-element-hover hover:text-fg active:bg-element-active focus-visible:border-focus',
        // A small action that stays in the background, for example "Restore all" above a list. As a toggle, it shows
        // when it is on.
        quiet:
          'border-transparent font-normal text-fg-muted hover:bg-element-hover hover:text-fg aria-pressed:bg-element-selected aria-pressed:text-fg',
        danger: 'border-danger bg-danger text-on-danger hover:bg-danger-hover active:bg-danger-hover',
        success: 'border-success bg-success text-on-success hover:bg-success-hover active:bg-success-hover',
        link: 'border-transparent text-accent-fg underline-offset-4 hover:underline'
      },
      size: {
        xs: 'h-ui-xs gap-1 px-1 text-sm',
        sm: 'h-ui-sm gap-1 px-1.5 text-base',
        md: 'h-ui-md gap-1.5 px-2 text-lg',
        lg: 'h-ui-lg gap-1.5 px-3 text-xl',
        'icon-sm': 'size-ui-sm',
        icon: 'size-ui-md',
        'icon-lg': 'size-ui-lg'
      }
    },
    defaultVariants: {
      variant: 'default',
      size: 'sm'
    }
  });

  export type ButtonVariants = VariantProps<typeof buttonVariants>;
</script>

<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { HTMLButtonAttributes } from 'svelte/elements';

  import { cn } from '$lib/core/utils';

  import { Spinner } from './cn/spinner';

  interface Props extends HTMLButtonAttributes, ButtonVariants {
    class?: string;
    children?: Snippet;
    loading?: boolean;
  }

  let {
    variant = 'default',
    size = 'sm',
    class: className = '',
    children,
    loading = false,
    disabled = false,
    ...restProps
  }: Props = $props();
</script>

<button
  class={buttonVariants({ variant, size, class: cn('relative', className) })}
  disabled={disabled || loading}
  aria-busy={loading}
  {...restProps}
>
  {#if children}
    <span class={cn('inline-flex items-center justify-center gap-[inherit]', loading && 'invisible')}>
      {@render children()}
    </span>
  {/if}
  {#if loading}
    <Spinner class="absolute" />
  {/if}
</button>
