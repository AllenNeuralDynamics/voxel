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
          'border-line bg-transparent font-normal hover:border-line-selected hover:bg-element-hover hover:text-fg focus-visible:border-focus active:bg-element-active',
        // A dashed edge marks the place of an item to come, such as a button that adds to a list.
        dashed:
          'border-dashed border-control-line bg-transparent font-normal text-fg-muted hover:border-control-line-hover hover:bg-element-hover hover:text-fg focus-visible:border-focus active:bg-element-active',
        ghost:
          'border-transparent hover:bg-element-hover hover:text-fg focus-visible:border-focus active:bg-element-active',
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

  import { reportFailure } from '../failures';
  import { Spinner } from '../shadcn/spinner';
  import { cn } from '../utils/cn';
  import { delayedTrue } from '../utils/delayed-true.svelte';

  interface Props extends Omit<HTMLButtonAttributes, 'onclick'>, ButtonVariants {
    class?: string;
    children?: Snippet;
    /** The page waits for something that the button did not start. */
    loading?: boolean;
    /**
     * When it returns a promise, the button waits for it: it takes no other click, shows its spinner once the wait
     * passes 200 ms, and reports a failure.
     */
    onclick?: (event: MouseEvent & { currentTarget: EventTarget & HTMLButtonElement }) => unknown;
  }

  let {
    variant = 'default',
    size = 'sm',
    class: className = '',
    children,
    loading = false,
    disabled = false,
    onclick,
    ...restProps
  }: Props = $props();

  let waiting = $state(false);
  const slowWait = delayedTrue(() => waiting, 200);
  const spinning = $derived(loading || slowWait.current);

  function click(event: MouseEvent & { currentTarget: EventTarget & HTMLButtonElement }): void {
    const result = onclick?.(event);
    if (!(result instanceof Promise)) return;
    waiting = true;
    result.catch(reportFailure).finally(() => (waiting = false));
  }
</script>

<button
  class={buttonVariants({ variant, size, class: cn('relative', className) })}
  disabled={disabled || loading || waiting}
  aria-busy={loading || waiting}
  {...restProps}
  onclick={click}
>
  {#if children}
    <span class={cn('inline-flex items-center justify-center gap-[inherit]', spinning && 'invisible')}>
      {@render children()}
    </span>
  {/if}
  {#if spinning}
    <Spinner class="absolute" />
  {/if}
</button>
