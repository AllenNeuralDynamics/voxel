<script lang="ts" module>
  import type { HTMLAnchorAttributes, HTMLButtonAttributes } from 'svelte/elements';
  import { tv, type VariantProps } from 'tailwind-variants';

  import { cn, type WithElementRef } from '$lib/utils';

  export const buttonVariants = tv({
    base: "group/button inline-flex shrink-0 items-center justify-center whitespace-nowrap rounded border border-transparent font-medium transition-[color,background-color,border-color,transform] outline-none select-none focus-visible:ring-2 focus-visible:ring-focused focus-visible:ring-offset-2 focus-visible:ring-offset-canvas active:not-aria-[haspopup]:scale-[0.98] disabled:pointer-events-none disabled:opacity-80 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
    variants: {
      variant: {
        default: 'border-primary bg-primary text-primary-fg hover:bg-primary/90 active:bg-primary/80',
        outline:
          'border-input bg-transparent text-fg hover:border-border hover:bg-element-hover active:bg-element-active',
        secondary:
          'border-input bg-element-bg text-fg hover:border-border hover:bg-element-hover active:bg-element-active',
        ghost: 'text-fg-muted hover:bg-element-hover hover:text-fg active:bg-element-active',
        destructive: 'border-danger bg-danger text-danger-fg hover:bg-danger/90 active:bg-danger/80',
        link: 'text-primary underline-offset-4 hover:underline'
      },
      size: {
        default: 'h-ui-sm gap-1.5 px-2 text-lg',
        xs: "h-ui-xs gap-1 px-1.5 text-base [&_svg:not([class*='size-'])]:size-3",
        sm: "h-ui-sm gap-1.5 px-2 text-lg [&_svg:not([class*='size-'])]:size-3.5",
        lg: 'h-ui-md gap-2 px-3 text-xl',
        icon: 'size-ui-sm',
        'icon-xs': "size-ui-xs [&_svg:not([class*='size-'])]:size-3",
        'icon-sm': 'size-ui-xs',
        'icon-lg': 'size-ui-md'
      }
    },
    defaultVariants: {
      variant: 'default',
      size: 'default'
    }
  });

  export type ButtonVariant = VariantProps<typeof buttonVariants>['variant'];
  export type ButtonSize = VariantProps<typeof buttonVariants>['size'];

  export type ButtonProps = WithElementRef<HTMLButtonAttributes> &
    WithElementRef<HTMLAnchorAttributes> & {
      variant?: ButtonVariant;
      size?: ButtonSize;
    };
</script>

<script lang="ts">
  let {
    class: className,
    variant = 'default',
    size = 'default',
    ref = $bindable(null),
    href = undefined,
    type = 'button',
    disabled,
    children,
    ...restProps
  }: ButtonProps = $props();
</script>

{#if href}
  <!-- href is a public component prop and may point outside this SvelteKit application. -->
  <!-- eslint-disable svelte/no-navigation-without-resolve -->
  <a
    bind:this={ref}
    data-slot="button"
    class={cn(buttonVariants({ variant, size }), className)}
    href={disabled ? undefined : href}
    aria-disabled={disabled}
    role={disabled ? 'link' : undefined}
    tabindex={disabled ? -1 : undefined}
    {...restProps}
  >
    {@render children?.()}
  </a>
  <!-- eslint-enable svelte/no-navigation-without-resolve -->
{:else}
  <button
    bind:this={ref}
    data-slot="button"
    class={cn(buttonVariants({ variant, size }), className)}
    {type}
    {disabled}
    {...restProps}
  >
    {@render children?.()}
  </button>
{/if}
