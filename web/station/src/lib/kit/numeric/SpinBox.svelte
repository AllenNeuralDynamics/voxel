<script lang="ts" generics="Clearable extends boolean = false">
  import { type BoxProps, type NumberProps, useNumberModel } from './number.svelte';
  import NumberBox from './NumberBox.svelte';

  type Key = 'ArrowUp' | 'ArrowDown';

  /** A number in the box, with up and down buttons at its right end. */
  type Props = NumberProps<Clearable> & BoxProps;

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
    ref = $bindable(null),
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

  // A button presses an arrow key in the number. So a step takes the text that you typed, and it joins the edit of
  // a box that has focus.
  function press(key: Key, event: MouseEvent): void {
    ref?.dispatchEvent(new KeyboardEvent('keydown', { key, shiftKey: event.shiftKey, bubbles: true }));
  }
</script>

{#snippet stepper(key: Key, atLimit: boolean)}
  <!-- The buttons keep the focus where it is. -->
  <button
    type="button"
    tabindex={-1}
    aria-label={key === 'ArrowUp' ? 'Increment' : 'Decrement'}
    class="flex flex-1 cursor-pointer items-center justify-center px-1 text-fg-faint first:border-b first:border-control-line hover:bg-element-hover hover:text-fg disabled:cursor-not-allowed disabled:opacity-40"
    disabled={locked || atLimit}
    onmousedown={(event) => event.preventDefault()}
    onclick={(event) => press(key, event)}
  >
    <svg width="8" height="5" viewBox="0 0 8 5" fill="currentColor" aria-hidden="true">
      <path d={key === 'ArrowUp' ? 'M4 0L8 5H0L4 0Z' : 'M4 5L0 0H8L4 5Z'} />
    </svg>
  </button>
{/snippet}

<NumberBox bind:ref {model} {disabled} {...rest}>
  <div class="flex flex-col">
    {@render stepper('ArrowUp', model.max != null && model.value >= model.max)}
    {@render stepper('ArrowDown', model.min != null && model.value <= model.min)}
  </div>
</NumberBox>
