<script lang="ts">
  import { onDestroy, type Snippet } from 'svelte';
  import type { Attachment } from 'svelte/attachments';

  import NumericChrome from './_NumericChrome.svelte';
  import NumericSteppers from './_NumericSteppers.svelte';

  interface Props {
    value?: number | null;
    min?: number | null;
    max?: number | null;
    /** Valid-value spacing, in model units. */
    step?: number | null;
    /** Ordinary keyboard, wheel, stepper, and scrub increment, in model units. */
    increment?: number | null;
    /** Shift+arrow increment, in model units. */
    bigIncrement?: number | null;
    /** Model units per displayed unit. */
    displayScale?: number;
    decimals?: number;
    numCharacters?: number;
    align?: 'left' | 'right';
    prefix?: string;
    suffix?: string;
    disabled?: boolean;
    steppers?: boolean;
    controls?: Snippet;
    placeholder?: string;
    id?: string;
    oneditstart?: () => void | (() => void);
    oncommit?: (value: number | null) => void;
    size?: 'xs' | 'sm' | 'md' | 'lg';
    class?: string;
  }

  let {
    value = $bindable(null),
    min = null,
    max = null,
    step = null,
    increment = null,
    bigIncrement = null,
    displayScale = 1,
    decimals,
    numCharacters = 8,
    align = 'left',
    prefix,
    suffix,
    disabled = false,
    steppers = true,
    controls,
    placeholder,
    id,
    oneditstart,
    oncommit,
    size = 'xs',
    class: className = ''
  }: Props = $props();

  let editing = $state(false);
  let editingText = $state('');
  let input = $state<HTMLInputElement>();
  let editActive = false;
  let editChanged = false;
  let editInitial: number | null = null;
  let releaseEdit: (() => void) | undefined;

  function beginEdit() {
    if (editActive) return;
    editActive = true;
    editChanged = false;
    editInitial = value;
    releaseEdit = oneditstart?.() || undefined;
  }

  function finishEdit(commit = true) {
    if (!editActive) return;
    if (commit && editChanged) oncommit?.(value);
    else if (!commit && editChanged) value = editInitial;
    editActive = false;
    editChanged = false;
    releaseEdit?.();
    releaseEdit = undefined;
  }

  function normalizedIncrement(requested: number | null, fallback: number): number {
    const candidate = requested != null && requested > 0 ? requested : fallback;
    if (step != null && step > 0) return Math.max(1, Math.round(candidate / step)) * step;
    return candidate > 0 ? candidate : 1;
  }

  const effectiveIncrement = $derived(normalizedIncrement(increment, step != null && step > 0 ? step : 1));
  const effectiveBigIncrement = $derived(
    Math.max(effectiveIncrement, normalizedIncrement(bigIncrement, effectiveIncrement * 10))
  );

  function resolve(raw: number): number {
    let next = raw;
    if (min != null) next = Math.max(min, next);
    if (max != null) next = Math.min(max, next);
    if (step != null && step > 0) {
      const base = min ?? 0;
      next = base + Math.round((next - base) / step) * step;
      if (min != null) next = Math.max(min, next);
      if (max != null) next = Math.min(max, next);
    }
    return next;
  }

  const inputValue = $derived.by(() => {
    if (editing) return editingText;
    if (value == null) return '';
    const displayed = value / displayScale;
    if (decimals !== undefined) return displayed.toFixed(decimals);
    if (!Number.isFinite(displayed)) return String(displayed);
    return parseFloat(displayed.toPrecision(15)).toString();
  });

  function set(next: number | null) {
    const resolved = next == null ? null : resolve(next);
    if (!Object.is(resolved, value)) editChanged = true;
    value = resolved;
  }

  function stepBy(direction: 1 | -1, amount = effectiveIncrement) {
    if (disabled) return;
    const base = value ?? (direction > 0 ? (min ?? 0) - amount : (max ?? 0) + amount);
    set(base + direction * amount);
  }

  function commit() {
    if (editing) {
      editing = false;
      const text = editingText.trim();
      if (!text) set(null);
      else {
        const parsed = Number(text);
        if (Number.isFinite(parsed)) set(parsed * displayScale);
      }
    }
    finishEdit();
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === 'Enter') {
      commit();
      input?.blur();
      return;
    }
    if (event.key === 'Escape') {
      editing = false;
      finishEdit(false);
      input?.blur();
      return;
    }
    if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return;
    event.preventDefault();
    if (editing) {
      const parsed = Number(editingText);
      if (Number.isFinite(parsed)) set(parsed * displayScale);
      editing = false;
    }
    stepBy(event.key === 'ArrowUp' ? 1 : -1, event.shiftKey ? effectiveBigIncrement : effectiveIncrement);
  }

  function handleMouseDown(event: MouseEvent) {
    const element = event.currentTarget as HTMLInputElement;
    if (document.activeElement !== element) {
      event.preventDefault();
      element.focus();
    }
  }

  function handleWheel(event: WheelEvent) {
    if (!event.altKey || disabled) return;
    event.preventDefault();
    const wasActive = editActive;
    beginEdit();
    stepBy(event.deltaY < 0 ? 1 : -1);
    if (!wasActive) finishEdit();
  }

  const scrubber: Attachment<HTMLElement> = (node) => {
    let startX = 0;
    let startValue = 0;
    let potential = false;
    let dragging = false;

    const cleanup = () => {
      potential = false;
      dragging = false;
      document.body.style.cursor = '';
      document.removeEventListener('mousemove', move);
      document.removeEventListener('mouseup', finish);
      window.removeEventListener('blur', finish);
    };
    const finish = () => {
      if (dragging) finishEdit();
      cleanup();
    };
    const move = (event: MouseEvent) => {
      if (!potential && !dragging) return;
      const delta = event.clientX - startX;
      if (!dragging && Math.abs(delta) > 3) {
        dragging = true;
        beginEdit();
        document.body.style.cursor = 'ew-resize';
        event.preventDefault();
      }
      if (dragging) set(startValue + Math.round(delta) * effectiveIncrement);
    };
    const start = (event: MouseEvent) => {
      if (event.button !== 0 || disabled) return;
      potential = true;
      startX = event.clientX;
      startValue = value ?? min ?? 0;
      document.addEventListener('mousemove', move);
      document.addEventListener('mouseup', finish);
      window.addEventListener('blur', finish);
    };

    node.addEventListener('mousedown', start);
    return () => {
      node.removeEventListener('mousedown', start);
      if (dragging) finishEdit(false);
      cleanup();
    };
  };

  function stepOnce(direction: 1 | -1) {
    beginEdit();
    stepBy(direction);
    finishEdit();
  }

  onDestroy(() => finishEdit(false));
</script>

{#snippet defaultControls()}
  <NumericSteppers
    {disabled}
    canIncrement={value == null || max == null || value < max}
    canDecrement={value == null || min == null || value > min}
    onincrement={() => stepOnce(1)}
    ondecrement={() => stepOnce(-1)}
  />
{/snippet}

<NumericChrome
  {prefix}
  {suffix}
  {size}
  {disabled}
  prefixAttachment={scrubber}
  controls={controls ?? (steppers ? defaultControls : undefined)}
  class={className}
>
  <input
    bind:this={input}
    {id}
    type="text"
    inputmode="decimal"
    spellcheck={false}
    value={inputValue}
    {placeholder}
    style:width="{numCharacters + 1}ch"
    style:text-align={align}
    class="m-0 min-w-0 flex-1 border-none bg-transparent py-0 font-mono outline-none"
    {disabled}
    oninput={(event) => {
      editing = true;
      editingText = event.currentTarget.value;
    }}
    onfocus={(event) => {
      beginEdit();
      event.currentTarget.select();
    }}
    onmousedown={handleMouseDown}
    onblur={commit}
    onkeydown={handleKeydown}
    onwheel={handleWheel}
  />
</NumericChrome>
