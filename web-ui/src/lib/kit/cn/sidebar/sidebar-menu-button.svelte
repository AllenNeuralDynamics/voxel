<script lang="ts" module>
  import { tv, type VariantProps } from 'tailwind-variants';

  export const sidebarMenuButtonVariants = tv({
    base: 'peer/menu-button group/menu-button flex w-full items-center gap-2 overflow-hidden rounded p-2 text-left text-lg font-normal text-fg-muted outline-hidden transition-[width,height,padding,color,background-color] hover:bg-element-hover hover:text-fg focus-visible:ring-2 focus-visible:ring-focused active:bg-element-active active:text-fg data-open:hover:bg-element-hover data-open:hover:text-fg data-active:bg-element-selected data-active:text-fg group-has-data-[sidebar=menu-action]/menu-item:pr-8 group-data-[collapsible=icon]:size-ui-sm! group-data-[collapsible=icon]:p-2! disabled:pointer-events-none disabled:opacity-50 aria-disabled:pointer-events-none aria-disabled:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0 [&>span:last-child]:truncate',
    variants: {
      variant: {
        default: 'hover:bg-element-hover hover:text-fg',
        outline:
          'bg-transparent shadow-[0_0_0_1px_var(--border)] hover:bg-element-hover hover:text-fg hover:shadow-[0_0_0_1px_var(--border-focused)]'
      },
      size: {
        default: 'h-ui-sm text-lg',
        sm: 'h-ui-xs text-base',
        lg: 'h-ui-md text-lg group-data-[collapsible=icon]:p-0!'
      }
    },
    defaultVariants: {
      variant: 'default',
      size: 'default'
    }
  });

  export type SidebarMenuButtonVariant = VariantProps<typeof sidebarMenuButtonVariants>['variant'];
  export type SidebarMenuButtonSize = VariantProps<typeof sidebarMenuButtonVariants>['size'];
</script>

<script lang="ts">
  import { mergeProps } from 'bits-ui';
  import type { ComponentProps, Snippet } from 'svelte';
  import type { HTMLAttributes } from 'svelte/elements';

  import * as Tooltip from '$lib/kit/cn/tooltip';
  import { cn, type WithElementRef, type WithoutChildrenOrChild } from '$lib/utils';

  import { useSidebar } from './context.svelte';

  let {
    ref = $bindable(null),
    class: className,
    children,
    child,
    variant = 'default',
    size = 'default',
    isActive = false,
    tooltipContent,
    tooltipContentProps,
    ...restProps
  }: WithElementRef<HTMLAttributes<HTMLButtonElement>, HTMLButtonElement> & {
    isActive?: boolean;
    variant?: SidebarMenuButtonVariant;
    size?: SidebarMenuButtonSize;
    tooltipContent?: Snippet | string;
    tooltipContentProps?: WithoutChildrenOrChild<ComponentProps<typeof Tooltip.Content>>;
    child?: Snippet<[{ props: Record<string, unknown> }]>;
  } = $props();

  const sidebar = useSidebar();

  const buttonProps = $derived({
    class: cn(sidebarMenuButtonVariants({ variant, size }), className),
    'data-slot': 'sidebar-menu-button',
    'data-sidebar': 'menu-button',
    'data-size': size,
    'data-active': isActive ? '' : undefined,
    ...restProps
  });
</script>

{#snippet Button({ props }: { props?: Record<string, unknown> })}
  {@const mergedProps = mergeProps(buttonProps, props)}
  {#if child}
    {@render child({ props: mergedProps })}
  {:else}
    <button bind:this={ref} {...mergedProps}>
      {@render children?.()}
    </button>
  {/if}
{/snippet}

{#if !tooltipContent}
  {@render Button({})}
{:else}
  <Tooltip.Root>
    <Tooltip.Trigger>
      {#snippet child({ props })}
        {@render Button({ props })}
      {/snippet}
    </Tooltip.Trigger>
    <Tooltip.Content
      side="right"
      align="center"
      hidden={sidebar.state !== 'collapsed' || sidebar.isMobile}
      {...tooltipContentProps}
    >
      {#if typeof tooltipContent === 'string'}
        {tooltipContent}
      {:else if tooltipContent}
        {@render tooltipContent()}
      {/if}
    </Tooltip.Content>
  </Tooltip.Root>
{/if}
