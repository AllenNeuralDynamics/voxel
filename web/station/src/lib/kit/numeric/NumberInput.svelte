<script lang="ts" generics="Clearable extends boolean = false">
  import { cn } from '$lib/core/utils';

  import {
    altScroll,
    type InputProps,
    numberDisplay,
    type NumberProps,
    PageNumber,
    stepNumber,
    useNumberModel
  } from './number.svelte';

  /** The bare number, with no box. Put it in a frame of your own, or use NumberBox for the usual box. */
  type Props = NumberProps<Clearable> & InputProps;

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
    decimals,
    displayScale = 1,
    align = null,
    ref = $bindable(null),
    class: className,
    ...attributes
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

  // While you type, the box shows your text. It becomes a number when you press Enter or leave the box.
  let typing = $state(false);
  let text = $state('');
  const display = $derived(numberDisplay(model, { decimals, displayScale }));
  const shown = $derived(typing ? text : display.text(model.value));

  // The focus edit starts at the first change while the box has focus, and it ends when the box loses focus. Its
  // changes make 1 undo step, and Esc puts back its start value.
  let focused = false;
  let start: { value: number; waiting: boolean } | null = null;

  function begin(): void {
    if (!focused || start) return;
    start = { value: model.value, waiting: false };
    model.beginEdit();
  }

  /** Sends a value. A scroll waits a little, so the end of the edit sends its last value. */
  function change(next: number, throttled = false): void {
    if (locked) return;
    begin();
    if (start && throttled) start.waiting = true;
    model.patch(next, { throttled });
  }

  function commit(): void {
    if (!typing) return;
    typing = false;
    const trimmed = text.trim();
    if (!trimmed) {
      if (model instanceof PageNumber && model.clearable) {
        begin();
        model.clear();
      }
      return;
    }
    const parsed = Number(trimmed) * displayScale;
    if (Number.isFinite(parsed) && model.resolve(parsed) !== model.value) change(parsed);
  }

  /** Esc: puts back the value from the start of the focus edit. */
  function cancel(): void {
    typing = false;
    if (!start) return;
    const original = start.value;
    start = null;
    if (!Number.isNaN(original)) {
      if (original !== model.value) model.patch(original);
    } else if (model instanceof PageNumber) {
      model.clear();
    }
    model.cancelEdit();
  }

  function onkeydown(event: KeyboardEvent & { currentTarget: HTMLInputElement }): void {
    if (event.key === 'Enter') {
      commit();
      event.currentTarget.blur();
    } else if (event.key === 'Escape') {
      // Esc cancels the edit first, so it does not also close a dialog around the box.
      if (typing || (start && !Object.is(start.value, model.value))) event.stopPropagation();
      cancel();
      event.currentTarget.blur();
    } else if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
      event.preventDefault();
      commit();
      change(stepNumber(model, event.key === 'ArrowUp' ? 1 : -1, event.shiftKey));
    }
  }
</script>

<!-- A text input, not type="number", so that steps like "-" and "1." stay while you type. -->
<input
  bind:this={ref}
  type="text"
  inputmode="decimal"
  spellcheck={false}
  autocomplete="off"
  {...attributes}
  value={shown}
  disabled={locked}
  oninput={(event) => {
    begin();
    typing = true;
    text = event.currentTarget.value;
  }}
  onfocus={(event) => {
    focused = true;
    event.currentTarget.select();
  }}
  onblur={() => {
    commit();
    focused = false;
    if (!start) return;
    const { waiting } = start;
    start = null;
    if (waiting) model.endEdit();
    else model.cancelEdit();
  }}
  onmousedown={(event) => {
    // The first click selects the whole number, so you can type over it. A second click places the cursor.
    if (document.activeElement === event.currentTarget) return;
    event.preventDefault();
    event.currentTarget.focus();
  }}
  {onkeydown}
  style:width="{display.width + 2}ch"
  style:text-align={align ?? 'left'}
  class={cn(
    'm-0 box-content min-w-0 border-none bg-transparent p-0 font-mono outline-none selection:bg-accent-muted selection:text-fg placeholder:text-fg-faint disabled:cursor-not-allowed',
    className
  )}
  {@attach !locked && altScroll((direction) => change(stepNumber(model, direction), true))}
/>
