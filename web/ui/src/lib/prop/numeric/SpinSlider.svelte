<script lang="ts">
  import type { NumericModel } from '$lib/model';
  import { cn } from '$lib/utils';

  import SpinBox from './SpinBox.svelte';

  const H = {
    xs: 'h-ui-xs',
    sm: 'h-ui-sm',
    md: 'h-ui-md',
    lg: 'h-ui-lg'
  } as const;

  interface Props {
    model: NumericModel;
    decimals?: number;
    numCharacters?: number;
    align?: 'left' | 'right';
    prefix?: string;
    suffix?: string;
    disabled?: boolean;
    size?: keyof typeof H;
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
    size = 'xs',
    class: className = ''
  }: Props = $props();

  const sliderMin = $derived(model.min ?? 0);
  const sliderMax = $derived(model.max ?? 100);
  const sliderStep = $derived(model.step ?? 1);

  const fillPct = $derived(((model.value - sliderMin) / (sliderMax - sliderMin)) * 100);

  function handleInput(e: Event) {
    const v = parseFloat((e.currentTarget as HTMLInputElement).value);
    if (!isNaN(v)) model.patch(v, { throttled: true });
  }
  function handleChange(e: Event) {
    const v = parseFloat((e.currentTarget as HTMLInputElement).value);
    if (!isNaN(v)) model.patch(v);
  }
</script>

<div
  class={cn(
    'flex min-w-0 items-stretch rounded bg-element-bg',
    H[size],
    disabled && 'pointer-events-none opacity-50',
    className
  )}
>
  <SpinBox
    {model}
    {decimals}
    {numCharacters}
    {align}
    {prefix}
    {suffix}
    {disabled}
    {size}
    class="rounded-r-none border-r-0 bg-transparent"
  />
  <input
    type="range"
    class="slider-input focus:border-focused min-w-16 flex-1 cursor-pointer appearance-none overflow-hidden rounded-r border border-input bg-transparent transition-colors outline-none"
    min={sliderMin}
    max={sliderMax}
    step={sliderStep}
    value={model.value}
    oninput={handleInput}
    onchange={handleChange}
    style="--fill-percentage: {fillPct}%"
  />
</div>

<style>
  .slider-input {
    --track-filled: var(--color-primary-soft);
    --thumb-width: 3px;
    margin: 0;
    padding: 0;
  }

  .slider-input:hover {
    --track-filled: color-mix(in oklch, var(--color-primary-soft) 85%, var(--color-fg));
  }

  .slider-input::-webkit-slider-runnable-track {
    width: 100%;
    height: 92%;
    border-radius: 2px;
    background: linear-gradient(
      to right,
      var(--track-filled) 0%,
      var(--track-filled) var(--fill-percentage),
      transparent var(--fill-percentage),
      transparent 100%
    );
  }

  .slider-input::-webkit-slider-thumb {
    appearance: none;
    width: var(--thumb-width);
    height: 100%;
    background: var(--track-filled);
    background: var(--color-fg-muted);
    border: none;
    border-inline: 1px solid var(--color-canvas);
    cursor: ew-resize;
  }

  .slider-input::-moz-range-track {
    width: 100%;
    height: 100%;
    background: linear-gradient(
      to right,
      var(--track-filled) 0%,
      var(--track-filled) var(--fill-percentage),
      transparent var(--fill-percentage),
      transparent 100%
    );
  }

  .slider-input::-moz-range-thumb {
    appearance: none;
    width: var(--thumb-width);
    height: 100%;
    background: var(--track-filled);
    border: none;
    border-radius: 0;
    cursor: ew-resize;
  }
</style>
