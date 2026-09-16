<script lang="ts">
  import { cn } from '$lib/utils';

  import Input from './Input.svelte';
  import { type NumericSource, useNumericModel } from './model.svelte';

  const SIZE = {
    xs: 'h-ui-xs',
    sm: 'h-ui-sm',
    md: 'h-ui-md text-base',
    lg: 'h-ui-lg text-lg'
  } as const;

  interface Props {
    model: NumericSource;
    decimals?: number;
    /** Model units per displayed unit. */
    displayScale?: number;
    numCharacters?: number;
    align?: 'left' | 'right';
    prefix?: string;
    suffix?: string;
    disabled?: boolean;
    steppers?: boolean;
    size?: keyof typeof SIZE;
    class?: string;
  }

  let {
    model: source,
    decimals,
    displayScale = 1,
    numCharacters = 8,
    align = 'left',
    prefix,
    suffix,
    disabled = false,
    steppers = true,
    size = 'xs',
    class: className = ''
  }: Props = $props();

  const model = useNumericModel(() => source);
  const effectiveDisabled = $derived(disabled || model.disabled);

  function increment() {
    model.patch(model.value + (model.step ?? 1));
  }
  function decrement() {
    model.patch(model.value - (model.step ?? 1));
  }
</script>

<div
  class={cn(
    'focus-within:border-focused inline-flex items-center overflow-hidden rounded border border-control-line bg-element-bg leading-none transition-colors hover:bg-element-hover',
    SIZE[size],
    effectiveDisabled && 'pointer-events-none opacity-50',
    className
  )}
>
  {#if prefix}
    <span class="shrink-0 px-1.5 font-mono text-fg-muted select-none" {@attach model.scrubber}>
      {prefix}
    </span>
  {/if}
  <Input
    {model}
    {decimals}
    {displayScale}
    {numCharacters}
    {align}
    disabled={effectiveDisabled}
    class={cn('min-w-0 flex-1 leading-none', prefix ? 'pl-0.5' : 'pl-1.5', suffix || steppers ? 'pr-0.5' : 'pr-1.5')}
  />
  {#if suffix}
    <span class="pointer-events-none shrink-0 px-1.5 font-mono text-fg-muted">{suffix}</span>
  {/if}
  {#if steppers}
    <div class="flex shrink-0 cursor-pointer flex-col self-stretch border-l border-control-line">
      <button
        type="button"
        class="flex flex-1 items-center justify-center rounded-tr border-b border-control-line bg-transparent px-1 text-fg-faint transition-colors hover:bg-element-hover hover:text-fg disabled:cursor-not-allowed disabled:opacity-40"
        onclick={increment}
        disabled={effectiveDisabled || (model.max != null && model.value >= model.max)}
        aria-label="Increment"
      >
        <svg width="8" height="5" viewBox="0 0 8 5" fill="currentColor"><path d="M4 0L8 5H0L4 0Z" /></svg>
      </button>
      <button
        type="button"
        class="flex flex-1 items-center justify-center rounded-br bg-transparent px-1 text-fg-faint transition-colors hover:bg-element-hover hover:text-fg disabled:cursor-not-allowed disabled:opacity-40"
        onclick={decrement}
        disabled={effectiveDisabled || (model.min != null && model.value <= model.min)}
        aria-label="Decrement"
      >
        <svg width="8" height="5" viewBox="0 0 8 5" fill="currentColor"><path d="M4 5L0 0H8L4 5Z" /></svg>
      </button>
    </div>
  {/if}
</div>
