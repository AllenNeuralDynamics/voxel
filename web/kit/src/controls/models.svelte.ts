import type { Attachment } from 'svelte/attachments';
import { SvelteSet } from 'svelte/reactivity';

import { decimalsOf } from './numeric/decimals';

/**
 * Linked models merge their bounds and options and patch together. Change membership only through this class so
 * each member's `group` back-reference stays in sync.
 */
export class LinkGroup<M extends { group?: LinkGroup<M> }> {
  members = $state(new SvelteSet<M>());

  add(model: M): void {
    if (model.group === this) return;
    model.group?.remove(model);
    this.members.add(model);
    model.group = this;
  }

  remove(model: M): void {
    if (!this.members.delete(model)) return;
    if (model.group === this) model.group = undefined;
  }

  /** Detach every member when unlinked, the active profile changes, or the session closes. */
  dissolve(): void {
    for (const m of this.members) this.remove(m);
  }
}

export type PropertyKind = 'integer' | 'float' | 'string' | 'bool' | 'generic';

/** Identifies consecutive replacements of one target during a continuous edit. */
export interface EditContext {
  editId?: string;
}

export interface PropOptions<T> {
  onPatch?: (value: T, context: EditContext) => void;
  disabled?: () => boolean;
}

/**
 * Mirrors the backend PropertyModel payload. Non-null `options` selects discrete choices for strings, integers, or
 * floats. Otherwise, numeric properties use minimum/maximum/step. Constraints can change without a value change; an
 * empty options list permits no choices.
 */
export interface PropSnapshot<T> {
  kind: PropertyKind;
  value: T;
  minimum?: number | null;
  maximum?: number | null;
  step?: number | null;
  options?: T[] | null;
}

export abstract class BasePropModel<T> {
  // `undefined as T` is a placeholder until the constructor assigns the real value; declaring it here spares each
  // subclass a field-init clash.
  value: T = $state(undefined as T);

  /** Mutated only via `LinkGroup.add/remove`. Typed `LinkGroup<this>` so each subclass gets a group of its class. */
  group: LinkGroup<this> | undefined = $state(undefined);

  #onPatch?: (value: T, context: EditContext) => void;
  #disabled: () => boolean;

  constructor(value: T, opts: PropOptions<T> = {}) {
    this.value = value;
    this.#onPatch = opts.onPatch;
    this.#disabled = opts.disabled ?? (() => false);
  }

  get disabled(): boolean {
    return this.#disabled();
  }

  /**
   * Sync from an authoritative source such as a backend echo. The snapshot is `<unknown>` so an `AnyPropModel` union
   * can dispatch without narrowing; `kind` already fixed the model's runtime type, so the cast is sound.
   */
  update(snapshot: PropSnapshot<unknown>): void {
    this.value = snapshot.value as T;
  }

  patch(value: T): void {
    if (this.disabled) return;
    if (this.group) {
      for (const peer of this.group.members) {
        if (peer.disabled) continue;
        peer.value = value;
        peer.publish(value);
      }
    } else {
      this.value = value;
      this.publish(value);
    }
  }

  dispose(): void {}

  /** Notify upstream without mutating local state. */
  protected publish(value: T, context: EditContext = {}): void {
    if (this.disabled) return;
    this.#onPatch?.(value, context);
  }
}

/** Fallback for kinds without a typed model, such as lists, dicts and dataclasses. */
export class PropModel extends BasePropModel<unknown> {}

export class StringModel extends BasePropModel<string> {}

export class BoolModel extends BasePropModel<boolean> {
  toggle(): void {
    this.patch(!this.value);
  }
}

export class EnumeratedModel<T extends string | number> extends BasePropModel<T> {
  #rawOptions: T[] = $state([] as T[]);

  get options(): T[] {
    if (!this.group) return this.#rawOptions;
    const group = this.group;
    return this.#rawOptions.filter((v) => {
      for (const peer of group.members) {
        if (peer === this) continue;
        if (!peer.#rawOptions.includes(v)) return false;
      }
      return true;
    });
  }

  constructor(value: T, options: T[], opts: PropOptions<T> = {}) {
    super(value, opts);
    this.#rawOptions = options;
  }

  update(snapshot: PropSnapshot<unknown>): void {
    super.update(snapshot);
    if (snapshot.options != null) this.#rawOptions = snapshot.options as T[];
  }

  select(value: T): void {
    if (!this.options.includes(value)) {
      console.warn('[EnumeratedModel] value not in options:', value, this.options);
      return;
    }
    this.patch(value);
  }

  cycle(direction: 1 | -1 = 1): void {
    const opts = this.options;
    if (opts.length === 0) return;
    const i = opts.indexOf(this.value);
    const next = (i + direction + opts.length) % opts.length;
    this.patch(opts[next]);
  }
}

export interface NumericOptions extends PropOptions<number> {
  min?: number | null;
  max?: number | null;
  step?: number | null;
  /** Shift+arrow step. Inferred from the range when omitted. */
  bigStep?: number | null;
  /** Double-click target for `scrubber`; null disables it. */
  home?: number | (() => number) | null;
  /** Continuous update interval in ms; 0 publishes immediately. */
  throttleMs?: number;
  /** Mark an unfinished edit; the returned callback releases it after submission or cancellation. */
  onEditStart?: () => () => void;
}

const DRAG_THRESHOLD_PX = 3;

/** Round to the nearest 1/2/5 × 10ⁿ "nice" value. */
function niceStep(x: number): number {
  if (!(x > 0)) return 0;
  const mag = 10 ** Math.floor(Math.log10(x));
  const n = x / mag;
  return (n < 1.5 ? 1 : n < 3.5 ? 2 : n < 7.5 ? 5 : 10) * mag;
}

export class NumericModel extends BasePropModel<number> {
  // Bounds from the backend; the public getters merge them across linked peers.
  #rawMin: number | null = $state(null);
  #rawMax: number | null = $state(null);
  #rawStep: number | null = $state(null);
  #rawBigStep: number | null = $state(null);

  home: number | (() => number) | null = $state(null);

  get min(): number | null {
    if (!this.group) return this.#rawMin;
    let m: number | null = this.#rawMin;
    for (const peer of this.group.members) {
      if (peer === this) continue;
      const pm = peer.#rawMin;
      if (pm != null) m = m == null ? pm : Math.max(m, pm);
    }
    return m;
  }

  get max(): number | null {
    if (!this.group) return this.#rawMax;
    let m: number | null = this.#rawMax;
    for (const peer of this.group.members) {
      if (peer === this) continue;
      const pm = peer.#rawMax;
      if (pm != null) m = m == null ? pm : Math.min(m, pm);
    }
    return m;
  }

  get step(): number | null {
    if (!this.group) return this.#rawStep;
    let s: number | null = this.#rawStep;
    for (const peer of this.group.members) {
      if (peer === this) continue;
      const ps = peer.#rawStep;
      if (ps != null) s = s == null ? ps : Math.max(s, ps);
    }
    return s;
  }

  get bigStep(): number {
    const step = this.step ?? 1;
    if (this.#rawBigStep != null) return this.#rawBigStep;
    const { min, max } = this;
    if (min != null && max != null && max > min) return Math.max(step, niceStep((max - min) / 10));
    return step * 10;
  }

  set bigStep(value: number | null) {
    this.#rawBigStep = value;
  }

  throttleMs: number;
  #throttleTimer: ReturnType<typeof setTimeout> | null = null;
  #pending: { value: number; context: EditContext } | null = null;
  #editId = $state<string | undefined>(undefined);
  #onEditStart?: () => () => void;
  #releaseEdit: (() => void) | undefined;

  constructor(value: number, opts: NumericOptions = {}) {
    super(value, opts);
    this.#rawMin = opts.min ?? null;
    this.#rawMax = opts.max ?? null;
    this.#rawStep = opts.step ?? null;
    this.#rawBigStep = opts.bigStep ?? null;
    this.home = opts.home ?? null;
    this.throttleMs = opts.throttleMs ?? 100;
    this.#onEditStart = opts.onEditStart;
  }

  resolve(raw: number): number {
    let v = raw;
    if (this.min != null && v < this.min) v = this.min;
    if (this.max != null && v > this.max) v = this.max;
    const step = this.step;
    if (step != null && step > 0) {
      const base = this.min ?? 0;
      // Rounding to the decimals of the steps drops float noise: 3 steps of 0.05 give 0.15, not 0.15000000000000002.
      const decimals = Math.max(decimalsOf(step), decimalsOf(base));
      v = Number((base + Math.round((v - base) / step) * step).toFixed(decimals));
      if (this.min != null && v < this.min) v = this.min;
      if (this.max != null && v > this.max) v = this.max;
    }
    return v;
  }

  /** Does not publish. */
  stage(raw: number): number {
    this.value = this.resolve(raw);
    return this.value;
  }

  /** Immediate by default, cancelling a pending throttle; `{ throttled: true }` coalesces calls within `throttleMs`. */
  patch(value: number, opts: { throttled?: boolean } = {}): void {
    if (this.disabled) return;
    const resolved = this.resolve(value);
    if (this.group) {
      for (const peer of this.group.members) peer.#setAndPublish(resolved, opts);
    } else {
      this.#setAndPublish(resolved, opts);
    }
  }

  #setAndPublish(value: number, opts: { throttled?: boolean }): void {
    if (this.disabled) return;
    this.value = value;
    const context: EditContext = this.#editId ? { editId: this.#editId } : {};
    if (opts.throttled && this.throttleMs > 0) {
      this.#releaseEdit ??= this.#onEditStart?.();
      this.#pending = { value, context };
      if (this.#throttleTimer !== null) return;
      this.#throttleTimer = setTimeout(() => {
        this.#throttleTimer = null;
        const pending = this.#pending;
        this.#pending = null;
        try {
          if (pending) this.publish(pending.value, pending.context);
        } finally {
          if (!this.#editId) {
            this.#releaseEdit?.();
            this.#releaseEdit = undefined;
          }
        }
      }, this.throttleMs);
    } else {
      if (this.#throttleTimer !== null) {
        clearTimeout(this.#throttleTimer);
        this.#throttleTimer = null;
      }
      this.#pending = null;
      try {
        this.publish(value, context);
      } finally {
        if (!this.#editId) {
          this.#releaseEdit?.();
          this.#releaseEdit = undefined;
        }
      }
    }
  }

  /** Start an edit; linked peers get separate IDs because they publish separate operations. */
  beginEdit(): void {
    for (const peer of this.group?.members ?? [this]) {
      if (!peer.disabled && !peer.#editId) {
        if (peer.#pending) peer.#setAndPublish(peer.#pending.value, {});
        peer.#releaseEdit ??= peer.#onEditStart?.();
        peer.#editId = crypto.randomUUID();
      }
    }
  }

  /** Flush a drag or delayed wheel update, retaining its edit ID when present. */
  endEdit(value = this.value): void {
    if (!this.#editId && !this.#pending) return;
    try {
      this.patch(value);
    } finally {
      this.cancelEdit();
    }
  }

  /** Discard delayed publications and release edit holds without reverting values or submitted writes. */
  cancelEdit(): void {
    for (const peer of this.group?.members ?? [this]) {
      if (peer.#throttleTimer !== null) clearTimeout(peer.#throttleTimer);
      peer.#throttleTimer = null;
      peer.#pending = null;
      peer.#editId = undefined;
      peer.#releaseEdit?.();
      peer.#releaseEdit = undefined;
    }
  }

  dispose(): void {
    this.cancelEdit();
  }

  /** Sync authoritative bounds without replacing the value under an active drag. */
  update(snapshot: PropSnapshot<unknown>): void {
    if (!this.#editId && !this.#pending) super.update(snapshot);
    if (snapshot.minimum !== undefined) this.#rawMin = snapshot.minimum;
    if (snapshot.maximum !== undefined) this.#rawMax = snapshot.maximum;
    if (snapshot.step !== undefined) this.#rawStep = snapshot.step;
  }

  wheel: Attachment<HTMLElement> = (node) => {
    const onWheel = (e: WheelEvent) => {
      if (!e.altKey) return;
      e.preventDefault();
      const direction = e.deltaY < 0 ? 1 : -1;
      this.patch(this.value + direction * (this.step ?? 1), { throttled: true });
    };
    node.addEventListener('wheel', onWheel, { passive: false });
    return () => node.removeEventListener('wheel', onWheel);
  };

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
        this.beginEdit();
        document.body.style.cursor = 'ew-resize';
        e.preventDefault();
      }
      if (!isDragging) return;
      this.patch(dragStartValue + Math.round(delta) * (this.step ?? 1), { throttled: true });
    };

    const onMouseUp = () => {
      if (isDragging) this.endEdit();
      isDragging = false;
      isPotentialDrag = false;
      document.body.style.cursor = '';
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
      window.removeEventListener('blur', onMouseUp);
    };

    const onMouseDown = (e: MouseEvent) => {
      if (e.button !== 0 || this.disabled) return;
      isPotentialDrag = true;
      dragStartX = e.clientX;
      dragStartValue = this.value;
      document.addEventListener('mousemove', onMouseMove);
      document.addEventListener('mouseup', onMouseUp);
      window.addEventListener('blur', onMouseUp);
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
      window.removeEventListener('blur', onMouseUp);
      if (isDragging) {
        document.body.style.cursor = '';
        this.cancelEdit();
      }
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

export function createPropModel(snapshot: PropSnapshot<unknown>, opts: PropOptions<unknown> = {}): AnyPropModel {
  const { disabled, onPatch } = opts;
  if (snapshot.options != null) {
    if (snapshot.kind === 'integer' || snapshot.kind === 'float') {
      return new EnumeratedModel<number>(snapshot.value as number, snapshot.options as number[], {
        disabled,
        onPatch: onPatch as ((v: number) => void) | undefined
      });
    }
    return new EnumeratedModel<string>(snapshot.value as string, snapshot.options as string[], {
      disabled,
      onPatch: onPatch as ((v: string) => void) | undefined
    });
  }
  switch (snapshot.kind) {
    case 'integer':
    case 'float':
      return new NumericModel(snapshot.value as number, {
        min: snapshot.minimum,
        max: snapshot.maximum,
        step: snapshot.step,
        disabled,
        onPatch: onPatch as ((v: number) => void) | undefined
      });
    case 'string':
      return new StringModel(snapshot.value as string, {
        disabled,
        onPatch: onPatch as ((v: string) => void) | undefined
      });
    case 'bool':
      return new BoolModel(snapshot.value as boolean, {
        disabled,
        onPatch: onPatch as ((v: boolean) => void) | undefined
      });
    case 'generic':
      return new PropModel(snapshot.value, { disabled, onPatch });
    default:
      // Unknown kind on the wire — degrade gracefully to fallback rather than throw.
      console.warn('[createPropModel] unknown kind, falling back to PropModel:', snapshot.kind);
      return new PropModel(snapshot.value, { disabled, onPatch });
  }
}
