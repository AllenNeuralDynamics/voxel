import type { Attachment } from 'svelte/attachments';

export interface NumericModelOptions {
  value?: number;
  min?: number | null;
  max?: number | null;
  step?: number | null;
  /** Double-click target for the `scrubber` attachment. Number, function, or null to disable. */
  home?: number | (() => number) | null;
  /** Callback invoked by `patch()` to propagate the value upstream (e.g. backend write). */
  onPatch?: (value: number) => void;
  /** Throttle interval in ms for `patch({ throttled: true })`. Defaults to 100. */
  throttleMs?: number;
}

export interface NumericModelSnapshot {
  value?: number;
  min?: number | null;
  max?: number | null;
  step?: number | null;
}

const DRAG_THRESHOLD_PX = 3;

export class NumericModel {
  value = $state<number>(0);
  min = $state<number | null>(null);
  max = $state<number | null>(null);
  step = $state<number | null>(null);
  home = $state<number | (() => number) | null>(null);

  #onPatch?: (value: number) => void;
  #throttleMs: number;
  #throttleTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(opts: NumericModelOptions = {}) {
    this.value = opts.value ?? 0;
    this.min = opts.min ?? null;
    this.max = opts.max ?? null;
    this.step = opts.step ?? null;
    this.home = opts.home ?? null;
    this.#onPatch = opts.onPatch;
    this.#throttleMs = opts.throttleMs ?? 100;
  }

  /** Pure: return what `raw` would resolve to (clamped to [min,max] and snapped to step). */
  resolve(raw: number): number {
    let v = raw;
    if (this.min != null && v < this.min) v = this.min;
    if (this.max != null && v > this.max) v = this.max;
    if (this.step != null && this.step > 0) {
      const base = this.min ?? 0;
      v = base + Math.round((v - base) / this.step) * this.step;
      if (this.min != null && v < this.min) v = this.min;
      if (this.max != null && v > this.max) v = this.max;
    }
    return v;
  }

  /** Resolve `raw` and assign to `value`. Local-only mutation — does not publish. */
  stage(raw: number): number {
    this.value = this.resolve(raw);
    return this.value;
  }

  /**
   * Publish the current (or a new) value upstream via the `onPatch` callback.
   * @param opts.value      If provided, stage this value first, then publish.
   * @param opts.throttled  Defer via internal throttle (defaults to 100ms).
   *                        An immediate `patch()` cancels any pending throttled fire.
   */
  patch(opts: { value?: number; throttled?: boolean } = {}): void {
    if (opts.value !== undefined) this.stage(opts.value);
    if (opts.throttled) {
      if (this.#throttleTimer !== null) return;
      this.#throttleTimer = setTimeout(() => {
        this.#throttleTimer = null;
        this.#onPatch?.(this.value);
      }, this.#throttleMs);
    } else {
      if (this.#throttleTimer !== null) {
        clearTimeout(this.#throttleTimer);
        this.#throttleTimer = null;
      }
      this.#onPatch?.(this.value);
    }
  }

  /** Sync from an authoritative source (e.g. backend). Does not clamp or snap. */
  update(snapshot: NumericModelSnapshot): void {
    if (snapshot.value !== undefined) this.value = snapshot.value;
    if (snapshot.min !== undefined) this.min = snapshot.min;
    if (snapshot.max !== undefined) this.max = snapshot.max;
    if (snapshot.step !== undefined) this.step = snapshot.step;
  }

  /** Alt+wheel scrubs the value by `step`. Attach to any element you want to be the gesture surface. */
  wheel: Attachment<HTMLElement> = (node) => {
    const onWheel = (e: WheelEvent) => {
      if (!e.altKey) return;
      e.preventDefault();
      const direction = e.deltaY < 0 ? 1 : -1;
      this.patch({ value: this.value + direction * (this.step ?? 1) });
    };
    node.addEventListener('wheel', onWheel, { passive: false });
    return () => node.removeEventListener('wheel', onWheel);
  };

  /** Click-and-drag horizontally to scrub; double-click snaps to `home` (if set). Attach to any drag-handle element. */
  scrubber: Attachment<HTMLElement> = (node) => {
    let dragStartX = 0;
    let dragStartValue = 0;
    let isDragging = false;
    let isPotentialDrag = false;

    const onMouseMove = (e: MouseEvent) => {
      if (!isPotentialDrag && !isDragging) return;
      const delta = e.clientX - dragStartX;
      if (!isDragging && Math.abs(delta) > DRAG_THRESHOLD_PX) {
        isDragging = true;
        document.body.style.cursor = 'ew-resize';
        e.preventDefault();
      }
      if (!isDragging) return;
      this.patch({
        value: dragStartValue + Math.round(delta) * (this.step ?? 1),
        throttled: true
      });
    };

    const onMouseUp = () => {
      if (isDragging) this.patch();
      isDragging = false;
      isPotentialDrag = false;
      document.body.style.cursor = '';
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
    };

    const onMouseDown = (e: MouseEvent) => {
      if (e.button !== 0) return;
      isPotentialDrag = true;
      dragStartX = e.clientX;
      dragStartValue = this.value;
      document.addEventListener('mousemove', onMouseMove);
      document.addEventListener('mouseup', onMouseUp);
    };

    const onDblClick = () => {
      if (this.home == null) return;
      const target = typeof this.home === 'function' ? this.home() : this.home;
      this.patch({ value: target });
    };

    node.addEventListener('mousedown', onMouseDown);
    node.addEventListener('dblclick', onDblClick);
    node.style.cursor = 'ew-resize';

    return () => {
      node.removeEventListener('mousedown', onMouseDown);
      node.removeEventListener('dblclick', onDblClick);
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
      node.style.cursor = '';
    };
  };
}
