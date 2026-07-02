<script lang="ts" module>
  import { tv, type VariantProps } from 'tailwind-variants';

  export const numberInputVariants = tv({
    slots: {
      wrapper: 'inline-flex items-center',
      input:
        'm-0 cursor-default border-none bg-transparent py-0 tabular-nums outline-none select-none focus:cursor-text',
      prefix: 'shrink-0 cursor-default whitespace-nowrap text-fg-muted select-none',
      suffix: 'pointer-events-none shrink-0 whitespace-nowrap text-fg-muted'
    },
    variants: {
      size: {
        xs: {
          input: 'leading-none px-0.5',
          prefix: 'leading-none px-0.5',
          suffix: 'leading-none px-0.5'
        },
        sm: {
          input: 'leading-none px-1',
          prefix: 'leading-none px-1',
          suffix: 'leading-none px-1'
        }
      }
    },
    defaultVariants: {
      size: 'xs'
    }
  });

  export type NumberInputVariants = VariantProps<typeof numberInputVariants>;
</script>

<script lang="ts">
  import { useEventListener, useThrottle } from 'runed';

  import { cn } from '$lib/utils';

  interface Props extends NumberInputVariants {
    value?: number;
    min?: number;
    max?: number;
    /** Grid resolution. All committed values round to ``min + n·step``. */
    step?: number;
    /**
     * Optional gesture step for drag / wheel. Defaults to ``step``.
     * Should be a multiple of ``step``; non-multiples still snap to the grid.
     */
    bigStep?: number;
    decimals?: number;
    numCharacters?: number;
    align?: 'left' | 'right';
    draggable?: boolean;
    scrollable?: boolean;
    prefix?: string;
    suffix?: string;
    /** Double-click preset target. */
    resetValue?: number | (() => number);
    disabled?: boolean;
    class?: string;
    onChange?: (newValue: number) => void;
  }

  let {
    value = $bindable(0),
    min = -Infinity,
    max = Infinity,
    step = 1,
    bigStep,
    decimals,
    numCharacters = 4,
    align = 'left',
    draggable = true,
    scrollable = true,
    prefix,
    suffix,
    resetValue,
    disabled = false,
    size = 'xs',
    class: className = '',
    onChange: onValueChange
  }: Props = $props();

  const styles = $derived(numberInputVariants({ size }));
  const gestureStep = $derived(bigStep ?? step);

  const throttledChange = useThrottle(
    (v: number) => onValueChange?.(v),
    () => 100
  );

  let isEditing = $state(false);
  let editingText = $state('');

  function snap(v: number): number {
    if (step <= 0 || !isFinite(step)) return v;
    if (!isFinite(min)) return Math.round(v / step) * step;
    return min + Math.round((v - min) / step) * step;
  }

  function commit(raw: number, opts: { throttled?: boolean } = {}) {
    const clamped = Math.max(min, Math.min(max, raw));
    const snapped = Math.max(min, Math.min(max, snap(clamped)));
    value = snapped;
    if (opts.throttled) {
      throttledChange(snapped);
    } else {
      onValueChange?.(snapped);
    }
  }

  function commitEdit() {
    if (!isEditing) return;
    isEditing = false;
    const parsed = parseFloat(editingText);
    if (isNaN(parsed)) return;
    commit(parsed);
  }

  let inputValue = $derived.by(() => {
    if (isEditing) return editingText;
    if (value === undefined || Number.isNaN(value)) return '';
    if (decimals !== undefined) return value.toFixed(decimals);
    return value.toString();
  });

  let wrapperElement = $state<HTMLDivElement | undefined>();

  let isDragging = $state(false);
  let isPotentialDrag = $state(false);
  let dragStartX = $state(0);
  let dragStartValue = $state(0);
  const DRAG_THRESHOLD_PX = 3;

  function handleMouseDown(e: MouseEvent) {
    if (e.button !== 0 || !draggable) return;
    isPotentialDrag = true;
    dragStartX = e.clientX;
    dragStartValue = value;
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  }

  function handleMouseMove(e: MouseEvent) {
    if (!isPotentialDrag && !isDragging) return;
    const deltaX = e.clientX - dragStartX;
    if (!isDragging && Math.abs(deltaX) > DRAG_THRESHOLD_PX) {
      isDragging = true;
      document.body.style.cursor = 'ew-resize';
      e.preventDefault();
    }
    if (!isDragging) return;
    commit(dragStartValue + Math.round(deltaX) * gestureStep, { throttled: true });
  }

  function handleMouseUp() {
    throttledChange.cancel();
    if (isDragging) onValueChange?.(value);
    isDragging = false;
    isPotentialDrag = false;
    document.body.style.cursor = '';
    document.removeEventListener('mousemove', handleMouseMove);
    document.removeEventListener('mouseup', handleMouseUp);
  }

  function handleDoubleClick() {
    if (resetValue === undefined) return;
    const resolved = typeof resetValue === 'function' ? resetValue() : resetValue;
    commit(resolved);
  }

  function handleInput(e: Event) {
    isEditing = true;
    editingText = (e.target as HTMLInputElement).value;
  }

  function stepBy(direction: number, coarse: boolean) {
    if (disabled) return;
    const base = isEditing ? parseFloat(editingText) : value;
    isEditing = false;
    commit((Number.isNaN(base) ? value : base) + direction * (coarse ? gestureStep : step));
  }

  function handleFocus(e: FocusEvent) {
    (e.currentTarget as HTMLInputElement).select();
  }

  // First click selects the whole value (type-to-replace); once focused, a further click places the caret to edit.
  function handleInputMouseDown(e: MouseEvent) {
    const input = e.currentTarget as HTMLInputElement;
    if (document.activeElement !== input) {
      e.preventDefault();
      input.focus();
    }
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') {
      commitEdit();
      (e.target as HTMLInputElement)?.blur();
    } else if (e.key === 'Escape') {
      isEditing = false;
      (e.target as HTMLInputElement)?.blur();
    } else if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
      e.preventDefault();
      stepBy(e.key === 'ArrowUp' ? 1 : -1, e.shiftKey);
    }
  }

  // Alt-gated to avoid stealing the page scroll when the cursor passes over.
  function handleWheel(e: WheelEvent) {
    if (disabled || !scrollable || !e.altKey) return;
    e.preventDefault();
    const direction = e.deltaY < 0 ? 1 : -1;
    commit(value + direction * gestureStep);
  }

  useEventListener(() => wrapperElement, 'wheel', handleWheel, { passive: false });

  $effect(() => () => {
    document.removeEventListener('mousemove', handleMouseMove);
    document.removeEventListener('mouseup', handleMouseUp);
  });
</script>

<div bind:this={wrapperElement} class={cn(styles.wrapper(), disabled && 'pointer-events-none opacity-50', className)}>
  {#if prefix}
    <span
      role="button"
      tabindex="-1"
      onmousedown={draggable ? handleMouseDown : undefined}
      ondblclick={resetValue !== undefined ? handleDoubleClick : undefined}
      class={cn(styles.prefix(), draggable && 'cursor-ew-resize')}>{prefix}</span
    >
  {/if}
  <input
    type="text"
    value={inputValue}
    oninput={handleInput}
    onfocus={handleFocus}
    onmousedown={handleInputMouseDown}
    onblur={commitEdit}
    onkeydown={handleKeydown}
    style:width="{numCharacters + 1}ch"
    style:text-align={align}
    class={styles.input()}
  />
  {#if suffix}
    <span class={styles.suffix()}>{suffix}</span>
  {/if}
</div>
