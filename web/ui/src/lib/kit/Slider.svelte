<script lang="ts">
  import { useEventListener, useThrottle } from 'runed';

  interface Props {
    value?: number;
    target: number;
    min?: number;
    max?: number;
    step?: number;
    throttle?: number;
    orientation?: 'horizontal' | 'vertical';
    onChange?: (value: number) => void;
    class?: string;
  }

  let {
    value,
    target,
    min = 0,
    max = 100,
    step = 1,
    throttle = 0,
    orientation = 'horizontal',
    onChange,
    class: className = ''
  }: Props = $props();

  const fillPercentage = $derived(
    value != null ? ((value - min) / (max - min)) * 100 : ((target - min) / (max - min)) * 100
  );

  let inputElement = $state<HTMLInputElement | undefined>();

  const throttledChange = useThrottle(
    (v: number) => {
      onChange?.(v);
    },
    () => throttle
  );

  function handleInput(e: Event) {
    if (!onChange) return;
    throttledChange(parseFloat((e.currentTarget as HTMLInputElement).value));
  }

  function handleWheel(e: WheelEvent) {
    if (!e.altKey) return;
    e.preventDefault();
    const direction = e.deltaY < 0 ? 1 : -1;
    const newValue = Math.max(min, Math.min(max, target + direction * step));
    onChange?.(newValue);
  }

  useEventListener(() => inputElement, 'wheel', handleWheel, { passive: false });
</script>

<input
  bind:this={inputElement}
  type="range"
  {min}
  {max}
  {step}
  value={target}
  oninput={throttle > 0 ? handleInput : undefined}
  onchange={(e) => {
    throttledChange.cancel();
    onChange?.(parseFloat(e.currentTarget.value));
  }}
  class="slider {orientation} {className}"
  style="--fill-percentage: {fillPercentage}%"
/>

<style>
  .slider {
    width: 100%;
    appearance: none;
    outline: none;
    cursor: pointer;
    background: transparent;
    --track-filled: var(--color-primary);
    --track-unfilled: var(--color-element-bg);
    --thumb-color: var(--track-filled);
    --track-radius: 0.2rem;
    --thumb-width: 4px;
    --track-height: 0.75rem;
    --thumb-radius: var(--thumb-width);
    --thumb-height: calc(var(--track-height) * 2);
    --thumb-margin-block: calc((var(--track-height) / 2 - var(--thumb-height) / 2) - 0.5px);
    --track-border: 1px solid color-mix(in oklch, var(--color-fg-faint) 60%, transparent);
  }

  .slider:hover,
  .slider:focus,
  .slider:active {
    --track-filled: color-mix(in oklch, var(--color-primary) 50%, var(--color-fg));
    --track-unfilled: var(--color-element-hover);
    --track-border: 1px solid var(--color-border-focused);
  }

  .slider::-webkit-slider-runnable-track {
    width: 100%;
    height: var(--track-height);
    background: linear-gradient(
      to right,
      var(--track-filled) 0%,
      var(--track-filled) var(--fill-percentage),
      var(--track-unfilled) var(--fill-percentage),
      var(--track-unfilled) 100%
    );
    /*border: var(--track-border);*/
    border-radius: var(--track-radius);
    transition: background 150ms ease;
  }

  .slider::-webkit-slider-thumb {
    appearance: none;
    cursor: pointer;
    width: var(--thumb-width);
    height: var(--thumb-height);
    background: var(--thumb-color);
    margin-block: var(--thumb-margin-block);
    border-radius: var(--thumb-radius);
    border-inline: 1px solid var(--track-unfilled);
  }

  .slider::-moz-range-track {
    width: 100%;
    height: var(--track-height);
    background: var(--track-unfilled);
    border: var(--track-border);
    border-radius: var(--track-radius);
    transition: background 150ms ease;
  }

  .slider::-moz-range-progress {
    height: var(--track-height);
    background: var(--track-filled);
    border-radius: var(--track-radius) 0 0 var(--track-radius);
  }

  .slider::-moz-range-thumb {
    appearance: none;
    width: var(--thumb-width);
    height: var(--thumb-height);
    background: var(--thumb-color);
    border: none;
    border-radius: var(--thumb-radius);
    cursor: pointer;
  }

  /* Vertical: min at bottom, max at top. Width becomes the track thickness; height fills the container. */
  .slider.vertical {
    writing-mode: vertical-lr;
    direction: rtl;
    width: var(--track-height);
    height: 100%;
  }

  .slider.vertical::-webkit-slider-runnable-track {
    width: var(--track-height);
    height: 100%;
    background: linear-gradient(
      to top,
      var(--track-filled) 0%,
      var(--track-filled) var(--fill-percentage),
      var(--track-unfilled) var(--fill-percentage),
      var(--track-unfilled) 100%
    );
  }

  .slider.vertical::-webkit-slider-thumb {
    width: var(--thumb-height);
    height: var(--thumb-width);
    margin: 0 var(--thumb-margin-block);
  }

  .slider.vertical::-moz-range-track {
    width: var(--track-height);
    height: 100%;
  }

  .slider.vertical::-moz-range-thumb {
    width: var(--thumb-height);
    height: var(--thumb-width);
  }
</style>
