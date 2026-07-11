import type { Attachment } from 'svelte/attachments';
import { SvelteSet } from 'svelte/reactivity';

/**
 * Shared coordinator for N models linked together. Each member holds a back-reference via
 * its own `group` field; mutation goes exclusively through this class so the back-references
 * stay in sync. When linked, member models' bounds/options merge across peers and patches
 * propagate to all members.
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

  /** Detach every member; used when the owning UI surface unmounts or the active profile changes. */
  dissolve(): void {
    for (const m of [...this.members]) this.remove(m);
  }
}

export interface PropertyInfo {
  name: string;
  label: string;
  desc?: string | null;
  dtype: string;
  access: 'ro' | 'rw';
  units: string;
}

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
  minimum?: number | null;
  maximum?: number | null;
  step?: number | null;
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

  /**
   * Active link group, or undefined when this model is standalone. Mutated via `LinkGroup.add/remove`.
   * Typed `LinkGroup<this>` so subclasses get a concrete-class group automatically:
   * `NumericModel.group` is `LinkGroup<NumericModel>`, `EnumeratedModel<T>.group` is `LinkGroup<EnumeratedModel<T>>`, etc.
   */
  group: LinkGroup<this> | undefined = $state(undefined);

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

  /**
   * Set value locally and notify upstream via onPatch.
   * When linked, the value propagates to every peer in the group (each peer sets + publishes).
   */
  patch(value: T): void {
    if (this.group) {
      for (const peer of this.group.members) {
        peer.value = value;
        peer.publish(value);
      }
    } else {
      this.value = value;
      this.publish(value);
    }
  }

  /** Notify upstream without mutating local state. Subclasses use this when value was set some other way. */
  protected publish(value: T): void {
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
  #rawOptions: T[] = $state([] as T[]);

  /** Effective options: raw, intersected with peers' raw options when linked. */
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

  /** Sync value AND options from snapshot. */
  update(snapshot: PropSnapshot<unknown>): void {
    super.update(snapshot);
    if (snapshot.options != null) this.#rawOptions = snapshot.options as T[];
  }

  /** Patch to `value` if it's in current (merged) options; otherwise warn + no-op. */
  select(value: T): void {
    if (!this.options.includes(value)) {
      console.warn('[EnumeratedModel] value not in options:', value, this.options);
      return;
    }
    this.patch(value);
  }

  /** Patch to next (1) or previous (-1) option, wrapping. No-op when options is empty. */
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
  /** Coarse step for shift+arrow. Inferred from the range (or 10× step) when omitted. */
  bigStep?: number | null;
  /** Double-click target for the `scrubber` attachment. Number, function, or null to disable. */
  home?: number | (() => number) | null;
  /** Throttle interval in ms for `patch(value, { throttled: true })`. Defaults to 100. */
  throttleMs?: number;
}

const DRAG_THRESHOLD_PX = 3;

/** Round to the nearest 1/2/5 × 10ⁿ "nice" value. */
function niceStep(x: number): number {
  if (!(x > 0)) return 0;
  const mag = 10 ** Math.floor(Math.log10(x));
  const n = x / mag;
  return (n < 1.5 ? 1 : n < 3.5 ? 2 : n < 7.5 ? 5 : 10) * mag;
}

/**
 * Property model for numeric values with optional min/max/step constraints.
 *
 * Operations:
 *   - `patch(value)` — clamp/snap, set, publish (immediate; cancels any pending throttle)
 *   - `patch(value, { throttled: true })` — same, but coalesces calls within `throttleMs`
 *   - `resolve(raw)` — pure: returns what `raw` would clamp/snap to
 *   - `stage(raw)` — resolve + set, no publish
 *
 * Attachments:
 *   - `wheel` — alt+scroll scrubs the value by `step`
 *   - `scrubber` — click-and-drag horizontal scrub; double-click snaps to `home`
 */
export class NumericModel extends BasePropModel<number> {
  // Raw bounds — what the backend told us. Public accessors below merge across linked peers.
  #rawMin: number | null = $state(null);
  #rawMax: number | null = $state(null);
  #rawStep: number | null = $state(null);
  #rawBigStep: number | null = $state(null);

  home: number | (() => number) | null = $state(null);

  /** Effective minimum: raw, intersected with peers' raw mins (largest wins) when linked. */
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

  /** Effective maximum: raw, intersected with peers' raw maxes (smallest wins) when linked. */
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

  /** Effective step: raw, or the coarsest step across linked peers. */
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

  /** Coarse step: explicit `bigStep`, else a nice ~1/10-of-range value, else 10× step. */
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

  #throttleMs: number;
  #throttleTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(value: number, opts: NumericOptions = {}) {
    super(value, opts);
    this.#rawMin = opts.min ?? null;
    this.#rawMax = opts.max ?? null;
    this.#rawStep = opts.step ?? null;
    this.#rawBigStep = opts.bigStep ?? null;
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

  /**
   * Resolve, set, publish.
   * Default is immediate — cancels any pending throttle and fires now.
   * `{ throttled: true }` coalesces calls within `throttleMs`.
   * When linked, the resolved value propagates to every peer in the group; throttling
   * applies to NumericModel peers, non-numeric peers (theoretically possible since the
   * group type is `BasePropModel<number>`) just get an immediate set + publish.
   */
  patch(value: number, opts: { throttled?: boolean } = {}): void {
    // Resolve once at the entry — uses merged bounds when linked, raw bounds otherwise.
    const resolved = this.resolve(value);
    if (this.group) {
      for (const peer of this.group.members) peer.#setAndPublish(resolved, opts);
    } else {
      this.#setAndPublish(resolved, opts);
    }
  }

  /** Local-only: set this model's value and (throttled-)publish upstream. No group dispatch. */
  #setAndPublish(value: number, opts: { throttled?: boolean }): void {
    this.value = value;
    if (opts.throttled) {
      if (this.#throttleTimer !== null) return;
      this.#throttleTimer = setTimeout(() => {
        this.#throttleTimer = null;
        this.publish(this.value);
      }, this.#throttleMs);
    } else {
      if (this.#throttleTimer !== null) {
        clearTimeout(this.#throttleTimer);
        this.#throttleTimer = null;
      }
      this.publish(this.value);
    }
  }

  /** Sync value, min, max, step from authoritative source (e.g. backend echo). */
  update(snapshot: PropSnapshot<unknown>): void {
    super.update(snapshot);
    if (snapshot.minimum !== undefined) this.#rawMin = snapshot.minimum;
    if (snapshot.maximum !== undefined) this.#rawMax = snapshot.maximum;
    if (snapshot.step !== undefined) this.#rawStep = snapshot.step;
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
      this.patch(dragStartValue + Math.round(delta) * (this.step ?? 1), { throttled: true });
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
  NumericModel | EnumeratedModel<string> | EnumeratedModel<number> | BoolModel | StringModel | PropModel;

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
        min: snapshot.minimum,
        max: snapshot.maximum,
        step: snapshot.step,
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

/** A PropModel paired with its interface metadata. Profile saved-state lives on `Instrument.divergence`. */
export class Prop {
  readonly model: AnyPropModel;
  info: PropertyInfo = $state(undefined as never);

  constructor(model: AnyPropModel, info: PropertyInfo) {
    this.model = model;
    this.info = info;
  }

  get value(): unknown {
    return this.model.value;
  }
  get label(): string {
    return this.info.label || '';
  }
  get units(): string {
    return this.info.units ?? '';
  }
  get access() {
    return this.info.access;
  }
}
