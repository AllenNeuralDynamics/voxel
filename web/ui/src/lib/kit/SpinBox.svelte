<script lang="ts" module>
  import { tv, type VariantProps } from 'tailwind-variants';

  export const spinBoxVariants = tv({
    slots: {
      wrapper: ['items-center', 'transition-colors focus-within:border-focused select-none'],
      input: ['m-0 border-none bg-transparent py-0 font-mono text-fg outline-none select-none'],
      stack: ['flex cursor-pointer self-stretch flex-col border-l border-input'],
      stepButton: [
        'flex flex-1 items-center justify-center',
        'bg-transparent text-fg-faint',
        'transition-colors hover:bg-element-hover hover:text-fg',
        'disabled:cursor-not-allowed disabled:opacity-40'
      ],
      prefix: ['shrink-0 font-mono whitespace-nowrap', 'text-fg-muted select-none'],
      suffix: ['pointer-events-none font-mono text-fg-muted']
    },
    variants: {
      variant: {
        ghost: {
          wrapper: 'bg-transparent hover:border-fg/20'
        },
        filled: {
          wrapper: 'bg-element-bg hover:bg-element-hover'
        }
      },
      size: {
        xs: {
          wrapper: 'h-ui-xs rounded',
          input: 'text-xs leading-none px-0.5',
          prefix: 'text-xs leading-none',
          suffix: 'text-xs leading-none',
          stack: 'w-4'
        },
        sm: {
          wrapper: 'h-ui-sm rounded',
          input: 'text-xs leading-none px-0.5',
          prefix: 'text-xs leading-none',
          suffix: 'text-xs leading-none',
          stack: 'w-4'
        },
        md: {
          wrapper: 'h-ui-md rounded',
          input: 'text-sm leading-none px-0.5',
          prefix: 'text-sm leading-none',
          suffix: 'text-sm leading-none',
          stack: 'w-5'
        },
        lg: {
          wrapper: 'h-ui-lg rounded',
          input: 'text-base leading-none px-0.5',
          prefix: 'text-base leading-none',
          suffix: 'text-base leading-none',
          stack: 'w-5'
        }
      },
      appearance: {
        full: {
          wrapper: 'flex border border-input',
          input: 'flex-1 ps-1.5 pe-1',
          prefix: 'ps-1.5 pe-1',
          suffix: 'pe-1.5'
        },
        bordered: {
          wrapper: 'flex border border-input',
          input: 'flex-1 ps-1.5 pe-1',
          prefix: 'ps-1.5 pe-1',
          suffix: 'pe-1.5',
          stack: 'hidden'
        },
        inline: {
          wrapper: 'inline-flex border border-transparent',
          prefix: 'ps-1 pe-0.5',
          stack: 'hidden'
        }
      }
    },
    defaultVariants: {
      variant: 'filled',
      size: 'md',
      appearance: 'full'
    }
  });

  export type SpinBoxVariants = VariantProps<typeof spinBoxVariants>;
</script>

<script lang="ts">
  import { cn } from '$lib/utils';
  import { useEventListener, useThrottle } from 'runed';

  interface Props extends SpinBoxVariants {
    value?: number;
    min?: number;
    max?: number;
    /** Grid resolution. All committed values round to ``min + n·step``. */
    step?: number;
    /**
     * Optional gesture step for buttons / drag / wheel. Defaults to ``step``.
     * Should be a multiple of ``step``; non-multiples still snap to the grid.
     */
    bigStep?: number;
    decimals?: number;
    numCharacters?: number;
    color?: string;
    align?: 'left' | 'right';
    draggable?: boolean;
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
    color = 'inherit',
    align = 'left',
    variant = 'filled',
    appearance = 'full',
    draggable = true,
    prefix,
    suffix,
    resetValue,
    disabled = false,
    size = 'md',
    class: className = '',
    onChange: onValueChange
  }: Props = $props();

  const styles = $derived(spinBoxVariants({ variant, size, appearance }));
  const gestureStep = $derived(bigStep ?? step);

  const throttledDragCallback = useThrottle(
    (newValue: number) => {
      onValueChange?.(newValue);
    },
    () => 100
  );

  let isEditing = $state(false);
  let editingText = $state('');

  function snapToStep(v: number): number {
    if (step <= 0 || !isFinite(step)) return v;
    if (!isFinite(min)) return Math.round(v / step) * step;
    return min + Math.round((v - min) / step) * step;
  }

  function commit(raw: number, opts: { throttled?: boolean } = {}) {
    const clamped = Math.max(min, Math.min(max, raw));
    const snapped = Math.max(min, Math.min(max, snapToStep(clamped)));
    value = snapped;
    if (opts.throttled) {
      throttledDragCallback(snapped);
    } else {
      onValueChange?.(snapped);
    }
  }

  function commitEdit() {
    if (!isEditing) return;
    isEditing = false;
    const parsed = parseFloat(editingText);
    if (isNaN(parsed)) return; // discard invalid input
    commit(parsed);
  }

  let inputValue = $derived.by(() => {
    if (isEditing) return editingText;
    if (value === undefined || Number.isNaN(value)) return '';
    if (decimals !== undefined) return value.toFixed(decimals);
    return value.toString();
  });

  let inputElement = $state<HTMLInputElement | undefined>();
  let wrapperElement = $state<HTMLDivElement | undefined>();

  let isDragging = $state(false);
  let isPotentialDrag = $state(false);
  let dragStartX = $state(0);
  let dragStartValue = $state(0);
  const DRAG_THRESHOLD = 3;

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

    if (!isDragging && Math.abs(deltaX) > DRAG_THRESHOLD) {
      isDragging = true;
      document.body.style.cursor = 'ew-resize';
      e.preventDefault();
    }

    if (!isDragging) return;

    commit(dragStartValue + Math.round(deltaX) * gestureStep, { throttled: true });
  }

  function handleMouseUp() {
    throttledDragCallback.cancel();
    if (isDragging) {
      onValueChange?.(value);
    }
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
    const target = e.target as HTMLInputElement;
    isEditing = true;
    editingText = target.value;
  }

  function handleBlur() {
    commitEdit();
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') {
      commitEdit();
      (e.target as HTMLInputElement)?.blur();
    } else if (e.key === 'Escape') {
      isEditing = false;
      (e.target as HTMLInputElement)?.blur();
    }
  }

  function handleWheel(e: WheelEvent) {
    if (!e.altKey || !draggable) return;
    e.preventDefault();
    const direction = e.deltaY < 0 ? 1 : -1;
    commit(value + direction * gestureStep);
  }

  function increment() {
    commit(value + gestureStep);
  }

  function decrement() {
    commit(value - gestureStep);
  }

  useEventListener(() => wrapperElement, 'wheel', handleWheel, { passive: false });

  // Safety net: clean up drag listeners if component unmounts mid-drag
  $effect(() => {
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  });
</script>

<div
  bind:this={wrapperElement}
  class={cn(styles.wrapper({ class: className }), disabled && 'pointer-events-none border-input/50')}
>
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
    bind:this={inputElement}
    type="text"
    value={inputValue}
    oninput={handleInput}
    onblur={handleBlur}
    onkeydown={handleKeydown}
    style:width="{numCharacters + 1}ch"
    style:color
    style:text-align={align}
    class={styles.input()}
  />
  {#if suffix}
    <span class={styles.suffix()}>{suffix}</span>
  {/if}
  <div class={styles.stack()}>
    <button
      class={cn(styles.stepButton(), 'rounded-tr border-b border-input')}
      onclick={increment}
      disabled={value >= max}
      aria-label="Increment"
    >
      <svg width="8" height="5" viewBox="0 0 8 5" fill="currentColor"><path d="M4 0L8 5H0L4 0Z" /></svg>
    </button>
    <button
      class={cn(styles.stepButton(), 'rounded-br')}
      onclick={decrement}
      disabled={value <= min}
      aria-label="Decrement"
    >
      <svg width="8" height="5" viewBox="0 0 8 5" fill="currentColor"><path d="M4 5L0 0H8L4 5Z" /></svg>
    </button>
  </div>
</div>
