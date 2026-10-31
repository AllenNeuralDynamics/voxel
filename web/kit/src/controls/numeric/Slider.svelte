<script lang="ts">
  import type { HTMLInputAttributes } from 'svelte/elements';

  import { cn } from '../../utils/cn';
  import { box } from '../box';
  import { altScroll, rangeFraction, type SliderProps, stepNumber, useNumberModel } from './number.svelte';

  type Attributes = Omit<
    HTMLInputAttributes,
    'type' | 'value' | 'disabled' | 'class' | 'size' | 'min' | 'max' | 'step' | `on${string}` | `bind:${string}`
  >;

  /**
   * Drags a number between its limits. `track` is a thin line with a round thumb. `bar` is a box that fills up to
   * the value, so it lines up with the boxes in a dense row.
   */
  type Props = SliderProps &
    Attributes & {
      variant?: 'track' | 'bar';
      size?: 'sm' | 'lg';
      disabled?: boolean;
      class?: string;
    };

  let {
    value,
    onChange,
    model: given,
    min,
    max,
    step,
    bigStep,
    home,
    onEditStart,
    variant = 'track',
    size = 'sm',
    disabled = false,
    class: className,
    ...attributes
  }: Props = $props();

  const model = useNumberModel(() => ({
    value,
    onChange,
    model: given,
    min,
    max,
    step,
    bigStep,
    home,
    onEditStart,
    disabled
  }));
  const locked = $derived(disabled || model.disabled);
  const fraction = $derived(rangeFraction(model));

  // 1 drag is 1 edit. The drag sends its values a little apart, and its end sends the last one.
  let sliding = false;

  function slide(event: Event & { currentTarget: HTMLInputElement }): void {
    if (!sliding) {
      sliding = true;
      model.beginEdit();
    }
    model.patch(Number(event.currentTarget.value), { throttled: true });
  }

  function end(): void {
    if (sliding) model.endEdit();
    sliding = false;
  }
</script>

<!-- A native range input lies on top, so the keys, the clicks and the drags work as usual. -->
{#snippet range(thumb: string)}
  <input
    type="range"
    {...attributes}
    min={model.min}
    max={model.max}
    step={model.step ?? 'any'}
    value={fraction === null ? model.min : model.value}
    disabled={locked}
    oninput={slide}
    onchange={end}
    onblur={end}
    onpointercancel={end}
    class={cn(
      'absolute inset-0 m-0 size-full appearance-none bg-transparent opacity-0 disabled:cursor-not-allowed',
      '[&::-webkit-slider-thumb]:appearance-none',
      thumb
    )}
    {@attach !locked && altScroll((direction) => model.patch(stepNumber(model, direction), { throttled: true }))}
  />
{/snippet}

{#if variant === 'bar'}
  <!--
    The bar fills up to the value, and a thin line marks it. The fill shows an amount, so it takes the muted accent;
    the line is a mark, so it takes the accent fg color. The input thumb is as wide as the line, so they move together. The
    parts sit 1px inside the box, so the fill does not cover the box line.
  -->
  <div
    class={cn(
      box({ row: true, size, state: locked ? 'locked' : 'idle', hover: false }),
      'overflow-hidden p-px',
      className
    )}
  >
    <div class={cn('group relative min-w-16 flex-1', locked && 'opacity-50')}>
      {#if fraction !== null}
        <span
          class="pointer-events-none absolute inset-y-0 left-0 bg-accent-muted"
          style:width="calc(1px + (100% - 2px) * {fraction})"
        ></span>
        <span
          class="pointer-events-none absolute inset-y-0 w-[2px] bg-accent-fg"
          style:left="calc((100% - 2px) * {fraction})"
        ></span>
      {/if}
      {@render range(
        'cursor-ew-resize [&::-moz-range-thumb]:h-full [&::-moz-range-thumb]:w-[2px] [&::-webkit-slider-thumb]:h-full [&::-webkit-slider-thumb]:w-[2px]'
      )}
    </div>
  </div>
{:else}
  <!--
    The thumb is round: a round part is a handle that slides. Its center moves 6px inside each end. The fill takes
    the muted accent and the thumb takes the accent fg color. Focus shows outside the thumb, so it stays clear of the blue.
  -->
  <div
    class={cn(
      'group relative flex min-w-16 items-center',
      size === 'lg' ? 'h-ui-lg' : 'h-ui-sm',
      locked && 'opacity-50',
      className
    )}
  >
    <span class="pointer-events-none absolute inset-x-1.25 h-[3px] rounded-full bg-track"></span>
    {#if fraction !== null}
      <span
        class="pointer-events-none absolute left-1.25 h-[3px] rounded-full bg-accent-muted"
        style:width="calc((100% - 12px) * {fraction})"
      ></span>
      <span
        class="pointer-events-none absolute size-2.5 -translate-x-1/2 rounded-full bg-accent-fg group-has-focus-visible:outline-2 group-has-focus-visible:outline-offset-2 group-has-focus-visible:outline-focus"
        style:left="calc(6px + (100% - 12px) * {fraction})"
      ></span>
    {/if}
    {@render range('cursor-pointer [&::-moz-range-thumb]:size-[12px] [&::-webkit-slider-thumb]:size-[12px]')}
  </div>
{/if}
