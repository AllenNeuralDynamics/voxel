<script lang="ts" module>
  import { tv, type VariantProps } from 'tailwind-variants';

  export const nudgeVariants = tv({
    slots: {
      wrapper: 'flex items-center',
      button: [
        'flex items-center justify-center shrink-0 cursor-pointer transition-colors',
        'text-fg-muted hover:bg-element-hover hover:text-fg',
        'disabled:cursor-not-allowed disabled:opacity-40'
      ],
      body: 'grid flex-1 grid-cols-[auto_1fr_auto] items-center gap-1 select-none',
      prefix: 'font-mono text-fg-muted whitespace-nowrap',
      value: 'text-center font-mono tabular-nums text-fg',
      suffix: 'font-mono text-fg-muted whitespace-nowrap text-right'
    },
    variants: {
      size: {
        xs: {
          wrapper: 'h-ui-xs rounded text-xs',
          button: 'h-full w-5 text-xs',
          prefix: 'text-xs',
          value: 'text-xs',
          suffix: 'text-xs'
        },
        sm: {
          wrapper: 'h-ui-sm rounded text-xs',
          button: 'h-full w-6 text-xs',
          prefix: 'text-xs',
          value: 'text-xs',
          suffix: 'text-xs'
        },
        md: {
          wrapper: 'h-ui-md rounded text-sm',
          button: 'h-full w-7 text-sm',
          prefix: 'text-sm',
          value: 'text-sm',
          suffix: 'text-sm'
        }
      }
    },
    defaultVariants: {
      size: 'md'
    }
  });

  export type NudgeVariants = VariantProps<typeof nudgeVariants>;
</script>

<script lang="ts">
  import { Minus, Plus } from '$lib/icons';
  import { cn, useModifierHeld } from '$lib/utils';

  interface Props extends NudgeVariants {
    /** Step size per button click / scroll tick / arrow key */
    step?: number;
    /** Fine step size (Shift modifier for all interactions) */
    fineStep?: number;
    /** Number of decimal places to display */
    decimals?: number;
    /** Label prefix (e.g., "dX") */
    prefix?: string;
    /** Unit suffix (e.g., "mm") */
    suffix?: string;
    /** Callback fired with the delta value on each nudge */
    onNudge?: (delta: number) => void;
    /** Disabled state */
    disabled?: boolean;
    class?: string;
  }

  let {
    step = 0.1,
    fineStep,
    decimals = 4,
    prefix,
    suffix,
    onNudge,
    disabled = false,
    size = 'xs',
    class: className = ''
  }: Props = $props();

  const styles = $derived(nudgeVariants({ size }));
  const meta = useModifierHeld('meta');
  const metaHeld = $derived(meta.current);

  function activeStep(e?: { shiftKey?: boolean }): number {
    return fineStep !== undefined && e?.shiftKey ? fineStep : step;
  }

  // --- Nudge (fires delta + updates display) ---
  let stickyValue = $state(0);
  let gestureValue = $state(0);
  let gestureActive = $state(false);
  let scrollTimer: ReturnType<typeof setTimeout> | undefined;

  /** Discrete nudge — value persists in display until next action */
  function nudge(delta: number) {
    if (delta === 0) return;
    stickyValue = delta;
    onNudge?.(delta);
  }

  /** Continuous gesture nudge — value shows only while active */
  function gestureNudge(delta: number) {
    gestureValue += delta;
    onNudge?.(delta);
  }

  function resetGesture() {
    gestureActive = false;
    gestureValue = 0;
  }

  const displayValue = $derived(
    gestureActive && gestureValue !== 0
      ? gestureValue.toFixed(decimals)
      : stickyValue !== 0
        ? stickyValue.toFixed(decimals)
        : ''
  );

  // --- Typing mode ---
  let isEditing = $state(false);
  let editText = $state('');
  let inputEl = $state<HTMLInputElement | null>(null);

  function commitEdit() {
    if (!isEditing) return;
    isEditing = false;
    const val = parseFloat(editText);
    if (!Number.isNaN(val)) nudge(val);
  }

  function handleFocus() {
    isEditing = true;
    editText = '';
    if (inputEl) inputEl.value = '';
  }

  function handleBlur() {
    commitEdit();
    if (inputEl) inputEl.value = displayValue;
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') {
      commitEdit();
      inputEl?.blur();
    } else if (e.key === 'Escape') {
      isEditing = false;
      if (inputEl) inputEl.value = displayValue;
      inputEl?.blur();
    } else if (!isEditing && (e.key === 'ArrowUp' || e.key === 'ArrowRight')) {
      e.preventDefault();
      nudge(activeStep(e));
    } else if (!isEditing && (e.key === 'ArrowDown' || e.key === 'ArrowLeft')) {
      e.preventDefault();
      nudge(-activeStep(e));
    }
  }

  // --- Drag (Meta + pointer) ---
  const DRAG_THRESHOLD = 3;
  let isDragging = false;
  let dragStartX = 0;
  let pixelAccum = 0;

  function handlePointerDown(e: PointerEvent) {
    if (disabled || isEditing || !e.metaKey) return;
    dragStartX = e.clientX;
    pixelAccum = 0;
    gestureValue = 0;
    gestureActive = true;
    isDragging = false;
    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', handlePointerUp);
  }

  function handlePointerMove(e: PointerEvent) {
    const dx = e.clientX - dragStartX;
    if (!isDragging && Math.abs(dx) > DRAG_THRESHOLD) {
      isDragging = true;
      document.body.style.cursor = 'ew-resize';
    }
    if (!isDragging) return;

    const newPixels = Math.round(dx / 2);
    const pixelDelta = newPixels - pixelAccum;
    if (pixelDelta !== 0) {
      pixelAccum = newPixels;
      gestureNudge(pixelDelta * activeStep(e));
    }
  }

  function handlePointerUp() {
    window.removeEventListener('pointermove', handlePointerMove);
    window.removeEventListener('pointerup', handlePointerUp);
    document.body.style.cursor = '';

    if (!isDragging && !disabled) inputEl?.focus();
    isDragging = false;
    pixelAccum = 0;
    resetGesture();
  }

  // --- Scroll (Meta + wheel) ---
  function handleWheel(e: WheelEvent) {
    if (disabled || !e.metaKey) return;
    e.preventDefault();
    gestureActive = true;
    const direction = e.deltaY < 0 ? 1 : -1;
    gestureNudge(direction * activeStep(e));

    clearTimeout(scrollTimer);
    scrollTimer = setTimeout(resetGesture, 400);
  }
</script>

<div
  class={cn(styles.wrapper(), 'border border-border bg-element-bg', className)}
  onwheel={handleWheel}
  onkeydown={handleKeydown}
  tabindex={disabled ? -1 : 0}
  role="spinbutton"
  aria-valuenow={stickyValue}
  aria-label="{prefix} nudge"
>
  <button
    class={cn(styles.button(), 'rounded-l border-r border-border')}
    {disabled}
    onclick={() => nudge(-step)}
    tabindex={-1}
  >
    <Minus width="12" height="12" />
  </button>

  <div
    class={cn(styles.body(), metaHeld ? 'cursor-ew-resize' : 'cursor-default')}
    onpointerdown={handlePointerDown}
    role="group"
  >
    {#if prefix}
      <span class={styles.prefix()}>{prefix}</span>
    {/if}

    <input
      bind:this={inputEl}
      type="text"
      class={cn(styles.value(), 'w-full bg-transparent outline-none', metaHeld ? 'cursor-ew-resize' : 'cursor-default', gestureActive && gestureValue !== 0 ? 'text-info' : '')}
      value={displayValue}
      onfocus={handleFocus}
      oninput={(e) => { editText = e.currentTarget.value; }}
      onblur={handleBlur}
      placeholder={(0).toFixed(decimals)}
    />

    {#if suffix}
      <span class={styles.suffix()}>{suffix}</span>
    {/if}
  </div>

  <button
    class={cn(styles.button(), 'rounded-r border-l border-border')}
    {disabled}
    onclick={() => nudge(step)}
    tabindex={-1}
  >
    <Plus width="12" height="12" />
  </button>
</div>
