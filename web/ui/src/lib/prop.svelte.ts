import type { Attachment } from 'svelte/attachments';

/** Wire-format discriminator emitted by the backend on every PropertyModel payload. */
export type PropertyKind = 'integer' | 'float' | 'string' | 'bool' | 'generic';

export interface PropOptions<T> {
  /** Callback invoked when patch() publishes upstream (e.g. backend write). */
  onPatch?: (value: T) => void;
}

/**
 * Mirrors the backend PropertyModel payload (with snake_case fields translated
 * to camelCase). `kind` and `value` are always present; subclass-specific fields
 * are optional and consumed only by the model that cares about them.
 */
export interface PropSnapshot<T> {
  kind: PropertyKind;
  value: T;
  min?: number | null;
  max?: number | null;
  step?: number | null;
  target?: number | null;
  options?: T[] | null;
}

/**
 * Abstract base for all property models in $lib/models.
 *
 * Owns `value` and the upstream `onPatch` callback. Subclasses add
 * subclass-specific fields (options, min/max/step, ...) and operations
 * (toggle, select, resolve, ...) but inherit `value`, `update`, `patch`.
 */
export abstract class BasePropModel<T> {
  // The `undefined as T` is a contained lie: this $state lives ~microseconds with
  // an undefined value during construction before the constructor body overwrites
  // it with the real value. Subclasses don't redeclare `value`, so there's no
  // field-init clash and no per-subclass boilerplate.
  value: T = $state(undefined as T);

  #onPatch?: (value: T) => void;

  constructor(value: T, opts: PropOptions<T> = {}) {
    this.value = value;
    this.#onPatch = opts.onPatch;
  }

  /**
   * Sync from an authoritative source (e.g. backend echo). Override to handle subclass-specific fields.
   *
   * Snapshot is typed `<unknown>` (not `<T>`) so callers holding an `AnyPropModel` union can
   * dispatch updates without per-variant narrowing — the kind discriminator already determined
   * the model's runtime type, so the cast here is sound.
   */
  update(snapshot: PropSnapshot<unknown>): void {
    this.value = snapshot.value as T;
  }

  /** Set value locally and notify upstream via onPatch. */
  patch(value: T): void {
    this.value = value;
    this._publish(value);
  }

  /** Notify upstream without mutating local state. Subclasses use this when value was set some other way. */
  protected _publish(value: T): void {
    this.#onPatch?.(value);
  }
}

/**
 * Fallback model for properties whose `kind` doesn't map to a typed concrete
 * (lists, dicts, dataclasses, or any kind the frontend hasn't specialized for).
 * Consumers receive `value: unknown` and must narrow before use.
 */
export class PropModel extends BasePropModel<unknown> {}

export class StringModel extends BasePropModel<string> {}

export class BoolModel extends BasePropModel<boolean> {
  /** Flip the current value and publish. */
  toggle(): void {
    this.patch(!this.value);
  }
}

/**
 * Property model for values constrained to a fixed set of options.
 * Maps to backend `kind='string' | 'integer'` payloads with `options` set.
 *
 * Operations:
 *   - `select(value)` — patch to value if it's in the current options (warns + no-op otherwise)
 *   - `cycle(direction)` — patch to next/prev option, wrapping around
 */
export class EnumeratedModel<T extends string | number> extends BasePropModel<T> {
  // Same lie pattern as BasePropModel.value — placeholder set in constructor body.
  options: T[] = $state([] as T[]);

  constructor(value: T, options: T[], opts: PropOptions<T> = {}) {
    super(value, opts);
    this.options = options;
  }

  /** Sync value AND options from snapshot. */
  update(snapshot: PropSnapshot<unknown>): void {
    super.update(snapshot);
    if (snapshot.options != null) this.options = snapshot.options as T[];
  }

  /** Patch to `value` if it's in current options; otherwise warn + no-op (mirrors backend). */
  select(value: T): void {
    if (!this.options.includes(value)) {
      console.warn('[EnumeratedModel] value not in options:', value, this.options);
      return;
    }
    this.patch(value);
  }

  /** Patch to next (1) or previous (-1) option, wrapping. No-op when options is empty. */
  cycle(direction: 1 | -1 = 1): void {
    if (this.options.length === 0) return;
    const i = this.options.indexOf(this.value);
    const next = (i + direction + this.options.length) % this.options.length;
    this.patch(this.options[next]);
  }
}

export interface NumericOptions extends PropOptions<number> {
  min?: number | null;
  max?: number | null;
  step?: number | null;
  target?: number | null;
  /** Double-click target for the `scrubber` attachment. Number, function, or null to disable. */
  home?: number | (() => number) | null;
  /** Throttle interval in ms for `patchThrottled()`. Defaults to 100. */
  throttleMs?: number;
}

const DRAG_THRESHOLD_PX = 3;

/**
 * Property model for numeric values with optional min/max/step constraints
 * and an optional `target` (commanded vs measured, e.g. laser setpoint).
 *
 * Operations:
 *   - `patch(value)` — clamp/snap, set, publish (immediate)
 *   - `patchThrottled(value)` — same, but coalesces calls within `throttleMs`
 *   - `resolve(raw)` — pure: returns what `raw` would clamp/snap to
 *   - `stage(raw)` — resolve + set, no publish
 *
 * Attachments:
 *   - `wheel` — alt+scroll scrubs the value by `step`
 *   - `scrubber` — click-and-drag horizontal scrub; double-click snaps to `home`
 */
export class NumericModel extends BasePropModel<number> {
  min: number | null = $state(null);
  max: number | null = $state(null);
  step: number | null = $state(null);
  target: number | null = $state(null);
  home: number | (() => number) | null = $state(null);

  #throttleMs: number;
  #throttleTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(value: number, opts: NumericOptions = {}) {
    super(value, opts);
    this.min = opts.min ?? null;
    this.max = opts.max ?? null;
    this.step = opts.step ?? null;
    this.target = opts.target ?? null;
    this.home = opts.home ?? null;
    this.#throttleMs = opts.throttleMs ?? 100;
  }

  /** Pure: what `raw` would resolve to after clamping to [min,max] and snapping to step. */
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

  /** Resolve, set, publish (immediate). Cancels any pending throttled fire. */
  patch(value: number): void {
    if (this.#throttleTimer !== null) {
      clearTimeout(this.#throttleTimer);
      this.#throttleTimer = null;
    }
    this.value = this.resolve(value);
    this._publish(this.value);
  }

  /** Resolve, set, publish (throttled). Subsequent calls within `throttleMs` coalesce. */
  patchThrottled(value: number): void {
    this.value = this.resolve(value);
    if (this.#throttleTimer !== null) return;
    this.#throttleTimer = setTimeout(() => {
      this.#throttleTimer = null;
      this._publish(this.value);
    }, this.#throttleMs);
  }

  /** Sync value, min, max, step, target from authoritative source (e.g. backend echo). */
  update(snapshot: PropSnapshot<unknown>): void {
    super.update(snapshot);
    if (snapshot.min !== undefined) this.min = snapshot.min;
    if (snapshot.max !== undefined) this.max = snapshot.max;
    if (snapshot.step !== undefined) this.step = snapshot.step;
    if (snapshot.target !== undefined) this.target = snapshot.target;
  }

  /** Alt+wheel scrubs the value by `step`. Attach to any element to make it a gesture surface. */
  wheel: Attachment<HTMLElement> = (node) => {
    const onWheel = (e: WheelEvent) => {
      if (!e.altKey) return;
      e.preventDefault();
      const direction = e.deltaY < 0 ? 1 : -1;
      this.patch(this.value + direction * (this.step ?? 1));
    };
    node.addEventListener('wheel', onWheel, { passive: false });
    return () => node.removeEventListener('wheel', onWheel);
  };

  /** Click-and-drag horizontally to scrub; double-click snaps to `home` (if set). */
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
      this.patchThrottled(dragStartValue + Math.round(delta) * (this.step ?? 1));
    };

    const onMouseUp = () => {
      if (isDragging) this.patch(this.value);
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
      this.patch(target);
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

export type AnyPropModel =
  | NumericModel
  | EnumeratedModel<string>
  | EnumeratedModel<number>
  | BoolModel
  | StringModel
  | PropModel;

/**
 * Construct the appropriate PropModel subclass for a given snapshot.
 *
 * Dispatch:
 *   - `options` present → EnumeratedModel (typed by `kind`)
 *   - `kind` 'integer' | 'float' → NumericModel (with constraints if present)
 *   - `kind` 'string' → StringModel
 *   - `kind` 'bool' → BoolModel
 *   - `kind` 'generic' (or unknown) → PropModel fallback
 */
export function createPropModel(snapshot: PropSnapshot<unknown>, onPatch?: (value: unknown) => void): AnyPropModel {
  if (snapshot.options != null) {
    if (snapshot.kind === 'integer') {
      return new EnumeratedModel<number>(snapshot.value as number, snapshot.options as number[], {
        onPatch: onPatch as ((v: number) => void) | undefined
      });
    }
    return new EnumeratedModel<string>(snapshot.value as string, snapshot.options as string[], {
      onPatch: onPatch as ((v: string) => void) | undefined
    });
  }
  switch (snapshot.kind) {
    case 'integer':
    case 'float':
      return new NumericModel(snapshot.value as number, {
        min: snapshot.min,
        max: snapshot.max,
        step: snapshot.step,
        target: snapshot.target,
        onPatch: onPatch as ((v: number) => void) | undefined
      });
    case 'string':
      return new StringModel(snapshot.value as string, {
        onPatch: onPatch as ((v: string) => void) | undefined
      });
    case 'bool':
      return new BoolModel(snapshot.value as boolean, {
        onPatch: onPatch as ((v: boolean) => void) | undefined
      });
    case 'generic':
      return new PropModel(snapshot.value, { onPatch });
    default:
      // Unknown kind on the wire — degrade gracefully to fallback rather than throw.
      console.warn('[createPropModel] unknown kind, falling back to PropModel:', snapshot.kind);
      return new PropModel(snapshot.value, { onPatch });
  }
}
