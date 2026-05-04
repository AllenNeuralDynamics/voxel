<script lang="ts">
  import { cn } from '$lib/utils';

  import type { NumericModel } from '../models.svelte';
  import Input from './Input.svelte';

  interface Props {
    model: NumericModel;
    decimals?: number;
    numCharacters?: number;
    align?: 'left' | 'right';
    prefix?: string;
    suffix?: string;
    disabled?: boolean;
    class?: string;
  }

  let {
    model,
    decimals,
    numCharacters = 8,
    align = 'left',
    prefix,
    suffix,
    disabled = false,
    class: className = ''
  }: Props = $props();

  function increment() {
    model.patch(model.value + (model.step ?? 1));
  }
  function decrement() {
    model.patch(model.value - (model.step ?? 1));
  }
</script>

<div
  class={cn(
    'focus-within:border-focused inline-flex h-ui-xs items-center overflow-hidden rounded border border-input bg-element-bg text-xs leading-none transition-colors hover:bg-element-hover',
    disabled && 'pointer-events-none opacity-50',
    className
  )}
  {@attach model.wheel}
>
  {#if prefix}
    <span class="shrink-0 px-1.5 font-mono text-fg-muted select-none" {@attach model.scrubber}>
      {prefix}
    </span>
  {/if}
  <Input {model} {decimals} {numCharacters} {align} class="flex-1 px-0.5 leading-none" />
  {#if suffix}
    <span class="pointer-events-none shrink-0 px-1.5 font-mono text-fg-muted">{suffix}</span>
  {/if}
  <div class="flex cursor-pointer flex-col self-stretch border-l border-input">
    <button
      class="flex flex-1 items-center justify-center rounded-tr border-b border-input bg-transparent px-1 text-fg-faint transition-colors hover:bg-element-hover hover:text-fg disabled:cursor-not-allowed disabled:opacity-40"
      onclick={increment}
      disabled={model.max != null && model.value >= model.max}
      aria-label="Increment"
    >
      <svg width="8" height="5" viewBox="0 0 8 5" fill="currentColor"><path d="M4 0L8 5H0L4 0Z" /></svg>
    </button>
    <button
      class="flex flex-1 items-center justify-center rounded-br bg-transparent px-1 text-fg-faint transition-colors hover:bg-element-hover hover:text-fg disabled:cursor-not-allowed disabled:opacity-40"
      onclick={decrement}
      disabled={model.min != null && model.value <= model.min}
      aria-label="Decrement"
    >
      <svg width="8" height="5" viewBox="0 0 8 5" fill="currentColor"><path d="M4 5L0 0H8L4 5Z" /></svg>
    </button>
  </div>
</div>
