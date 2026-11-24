<script lang="ts" module>
  /** The space between 2 steps, in px. Closer ticks show more of the range and need a finer hand. */
  const GAPS = { sparse: 8, medium: 6.4, dense: 5.3 };
  /** How long the keys and the wheel wait for the next step before the value is sent. */
  const SEND_AFTER_MS = 400;
  /** The part of the way that the drawn ruler moves toward its target in each frame. */
  const EASE = 0.25;
</script>

<script lang="ts">
  import type { HTMLAttributes } from 'svelte/elements';

  import { cn } from '../../utils/cn';
  import { altScroll, type SliderProps, stepNumber, useNumberModel } from './number.svelte';

  type Attributes = Omit<
    HTMLAttributes<HTMLDivElement>,
    'class' | 'role' | 'tabindex' | `on${string}` | `bind:${string}`
  >;

  /**
   * Sets a number by small moves inside a large range, such as a focus position. A needle at the center marks the
   * value, and a ruler with 1 tick for each step moves under it: drag the ruler, or use the arrow keys or Alt+scroll.
   * The value is sent when the drag ends, or a moment after the last key or scroll. Use a Slider for a value whose
   * whole range means something.
   */
  type Props = SliderProps &
    Attributes & {
      /** What the device reports now. It shows as a fill from the needle to that value. */
      reading?: number | null;
      /** The space between 2 ticks. */
      ticks?: keyof typeof GAPS;
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
    reading = null,
    ticks = 'dense',
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
  const low = $derived(model.min ?? 0);
  const high = $derived(model.max ?? 0);
  // Without a step, the ruler has 200 ticks over the range.
  const tick = $derived(model.step && model.step > 0 ? model.step : (high - low) / 200 || 1);
  const gap = $derived(GAPS[ticks]);

  let canvas = $state<HTMLCanvasElement | null>(null);
  let width = $state(0);
  let height = $state(0);

  // What is drawn now: the value under the needle and the end of the reading's fill. Both ease toward their targets,
  // except during a drag, when the ruler follows the pointer.
  let center = NaN;
  let fill = NaN;
  let frame = 0;
  let drag: { x: number; from: number } | null = null;
  let sendTimer: ReturnType<typeof setTimeout> | undefined;

  function draw(): void {
    frame = 0;
    const context = canvas?.getContext('2d');
    if (!canvas || !context || width === 0 || height === 0) return;
    const target = model.value;
    if (Number.isNaN(center) || Number.isNaN(target)) center = target;
    if (!drag) center += (target - center) * EASE;
    const shown = reading ?? NaN;
    fill = Number.isNaN(fill) || Number.isNaN(shown) ? shown : fill + (shown - fill) * EASE;
    const near = (a: number, b: number) => Number.isNaN(b) || Math.abs(a - b) < tick / gap / 2;
    if (!drag && near(center, target)) center = target;
    if (near(fill, shown)) fill = shown;

    const ratio = window.devicePixelRatio || 1;
    if (canvas.width !== Math.round(width * ratio)) canvas.width = Math.round(width * ratio);
    if (canvas.height !== Math.round(height * ratio)) canvas.height = Math.round(height * ratio);
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.clearRect(0, 0, width, height);
    if (Number.isNaN(center)) return;

    const style = getComputedStyle(canvas);
    const color = (name: string) => style.getPropertyValue(name).trim();
    const middle = width / 2;
    const at = (v: number) => middle + ((v - center) / tick) * gap;
    const mid = height / 2;

    // The reading: a band from the needle to what the device reports.
    if (!Number.isNaN(fill)) {
      const end = Math.max(0, Math.min(width, at(fill)));
      context.fillStyle = color('--accent-muted');
      context.fillRect(Math.min(middle, end), mid - 2, Math.abs(end - middle), 4);
    }

    // The ticks: every 10th at full strength, every 5th lower, the rest lowest; all fade near the ends.
    context.fillStyle = color('--fg-muted');
    const first = Math.max(0, Math.ceil((center - low - (middle / gap) * tick) / tick));
    const last = Math.min(Math.round((high - low) / tick), Math.floor((center - low + (middle / gap) * tick) / tick));
    for (let index = first; index <= last; index++) {
      const x = at(low + index * tick);
      const fade = Math.min(1, Math.min(x, width - x) / (width * 0.15));
      const [strength, tall] = index % 10 === 0 ? [1, 0.6] : index % 5 === 0 ? [0.7, 0.45] : [0.45, 0.3];
      context.globalAlpha = strength * Math.max(0, fade);
      context.fillRect(Math.round(x) - 0.5, mid - (height * tall) / 2, 1, height * tall);
    }
    // A cap at each end of the range.
    context.globalAlpha = 1;
    for (const limit of [low, high]) {
      const x = at(limit);
      if (x >= 0 && x <= width) context.fillRect(Math.round(x) - 1, mid - height * 0.4, 2, height * 0.8);
    }

    // The needle: fixed at the center, with round ends.
    context.strokeStyle = color('--accent-fg');
    context.lineWidth = 2;
    context.lineCap = 'round';
    context.beginPath();
    context.moveTo(middle, 2);
    context.lineTo(middle, height - 2);
    context.stroke();

    if (drag || center !== target || !(fill === shown || Number.isNaN(shown))) redraw();
  }

  function redraw(): void {
    frame ||= requestAnimationFrame(draw);
  }

  // Draws again when what it shows changes: the value, the reading, the limits, the spacing or the size.
  $effect(() => {
    void [model.value, reading, low, high, tick, gap, width, height, locked];
    redraw();
  });

  // A new theme or mode changes the colors, which the canvas reads when it draws.
  $effect(() => {
    const observer = new MutationObserver(redraw);
    observer.observe(document.documentElement, { attributes: true });
    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
      clearTimeout(sendTimer);
    };
  });

  /** Shows `raw` on its step, and sends nothing yet. */
  function show(raw: number): void {
    if (sendTimer === undefined && !drag) model.beginEdit();
    model.stage(raw);
  }

  /** Sends the value that shows, as 1 edit. */
  function send(): void {
    clearTimeout(sendTimer);
    sendTimer = undefined;
    model.endEdit();
  }

  /** A step from the keys or the wheel: the value is sent once no other step follows. */
  function nudge(raw: number): void {
    if (locked) return;
    show(raw);
    clearTimeout(sendTimer);
    sendTimer = setTimeout(send, SEND_AFTER_MS);
  }

  function press(event: PointerEvent & { currentTarget: HTMLDivElement }): void {
    if (locked || event.button !== 0 || Number.isNaN(model.value)) return;
    if (sendTimer !== undefined) send();
    event.currentTarget.setPointerCapture(event.pointerId);
    event.currentTarget.focus();
    model.beginEdit();
    drag = { x: event.clientX, from: model.value };
  }

  function move(event: PointerEvent): void {
    if (!drag) return;
    // The ruler follows the pointer; the value snaps to steps, or to 10 steps with Shift.
    center = Math.max(low, Math.min(high, drag.from - ((event.clientX - drag.x) / gap) * tick));
    const coarse = tick * 10;
    model.stage(event.shiftKey ? low + Math.round((center - low) / coarse) * coarse : center);
    redraw();
  }

  function release(): void {
    if (!drag) return;
    drag = null;
    model.endEdit();
    redraw();
  }

  function key(event: KeyboardEvent): void {
    const steps: Record<string, number> = { ArrowRight: 1, ArrowUp: 1, ArrowLeft: -1, ArrowDown: -1 };
    const pages: Record<string, number> = { PageUp: 10, PageDown: -10 };
    let next: number;
    if (event.key in steps) next = stepNumber(model, steps[event.key] as 1 | -1, event.shiftKey);
    else if (event.key in pages) next = model.value + pages[event.key] * tick;
    else if (event.key === 'Home') next = low;
    else if (event.key === 'End') next = high;
    else return;
    event.preventDefault();
    nudge(next);
  }
</script>

<div
  {...attributes}
  role="slider"
  tabindex={locked ? -1 : 0}
  aria-valuemin={low}
  aria-valuemax={high}
  aria-valuenow={Number.isNaN(model.value) ? undefined : model.value}
  aria-disabled={locked}
  aria-orientation="horizontal"
  class={cn(
    'relative min-w-16 touch-none rounded-sm outline-none select-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus',
    size === 'lg' ? 'h-ui-lg' : 'h-ui-sm',
    locked ? 'cursor-not-allowed opacity-50' : 'cursor-ew-resize',
    className
  )}
  bind:clientWidth={width}
  bind:clientHeight={height}
  onpointerdown={press}
  onpointermove={move}
  onpointerup={release}
  onpointercancel={release}
  onkeydown={key}
  onblur={() => sendTimer !== undefined && send()}
  {@attach !locked && altScroll((direction) => nudge(stepNumber(model, direction)))}
>
  <canvas bind:this={canvas} class="pointer-events-none absolute inset-0 size-full"></canvas>
</div>
