<script lang="ts" generics="Clearable extends boolean = false">
  import type { Snippet } from 'svelte';

  import { cn } from '../../utils/cn';
  import { box } from '../box';
  import { type BoxProps, type NumberProps, useNumberModel } from './number.svelte';
  import NumberInput from './NumberInput.svelte';

  /** A number in the box. Parts that you put in it, like a button, go at its right end. */
  type Props = NumberProps<Clearable> &
    BoxProps & {
      /** The number takes the free width. Without it, the parts at the end take it, like a slider. */
      grow?: boolean;
      children?: Snippet;
    };

  let {
    value,
    onChange,
    model: given,
    clearable,
    min,
    max,
    step,
    bigStep,
    home,
    onEditStart,
    disabled = false,
    align = null,
    prefix,
    suffix,
    size = 'sm',
    variant = 'filled',
    subgrid = false,
    grow = true,
    ref = $bindable(null),
    children,
    class: className,
    ...rest
  }: Props = $props();

  const model = useNumberModel(() => ({
    value,
    onChange,
    model: given,
    clearable,
    min,
    max,
    step,
    bigStep,
    home,
    onEditStart,
    disabled
  }));
  const locked = $derived(disabled || model.disabled);
</script>

<!--
  The parts sit 1px inside the box, so a filled part does not cover the box line. A press on the box, on the free
  room of the number or on the suffix puts the cursor in the number. With `subgrid`, the number and the end take 2
  columns of the parent grid, with no gap between them.
-->
<div
  role="group"
  class={cn(
    box({ row: true, variant, size, state: locked ? 'locked' : 'idle' }),
    'overflow-hidden p-px font-mono',
    subgrid ? 'col-span-2 grid grid-cols-subgrid gap-x-0' : 'inline-flex',
    className
  )}
  onpointerdown={(event) => {
    const { part } = (event.target as HTMLElement).dataset;
    if (event.target !== event.currentTarget && part !== 'number' && part !== 'suffix') return;
    event.preventDefault();
    ref?.focus();
  }}
>
  <div data-part="number" class={cn('flex min-w-0', grow ? 'flex-1' : 'flex-none')}>
    {#if prefix}
      <span class="flex shrink-0 items-center px-1.5 text-fg-muted select-none" {@attach !locked && model.scrubber}>
        {prefix}
      </span>
    {/if}
    <NumberInput
      bind:ref
      {model}
      {disabled}
      align={align ?? (prefix || suffix ? 'right' : 'left')}
      {...rest}
      class={cn('flex-1', prefix ? 'pl-0.5' : 'pl-1.5', suffix || children ? 'pr-0.5' : 'pr-1.5')}
    />
    {#if suffix}
      <span data-part="suffix" class="flex shrink-0 items-center px-1.5 text-fg-muted select-none">{suffix}</span>
    {/if}
  </div>
  {#if children}
    <div class={cn('flex min-w-0 border-l border-control-line', grow ? 'shrink-0' : 'flex-1')}>
      {@render children()}
    </div>
  {/if}
</div>
