import { onDestroy, untrack } from 'svelte';
import type { Attachment } from 'svelte/attachments';
import type { HTMLInputAttributes } from 'svelte/elements';

import { reportFailure } from '$lib/core/failures';
// From its own file, not `$lib/core/model`: `PageNumber` extends it when this module loads, and `$lib/core/model` imports the
// kit through `$lib/features/issues`. Through `$lib/core/model`, the class would not exist yet when the model loads first.
import { type EditContext, NumericModel } from '$lib/core/model/prop.svelte';
import { decimalsOf } from '$lib/core/utils';

/** The limits and steps of a number. A `model` gives its own. */
export interface NumberLimits {
  min?: number | null;
  max?: number | null;
  /** Values snap to this step, and the arrow keys and the buttons move by it. */
  step?: number | null;
  /** Shift+arrow moves by this. By default it is about 1/10 of the range, or 10 steps. */
  bigStep?: number | null;
  /** A double-click on the prefix puts this value back. */
  home?: number | (() => number) | null;
  /** Starts a hold on the edit queue while you edit. The function that it returns ends the hold. */
  onEditStart?: () => () => void;
}

type RangeLimits = Omit<NumberLimits, 'min' | 'max'> & { min: number; max: number };

type ValueSource<Limits, Clearable extends boolean> = Limits & {
  /** No value shows an empty box. */
  value: number | null | undefined;
  /** Gets each change. The edit info groups the changes of 1 edit into 1 undo step. */
  onChange: (value: Clearable extends true ? number | null : number, edit: EditContext) => unknown;
  /** Clearing the box sends `null`. Without it, clearing the box puts back the last value. */
  clearable?: Clearable;
  model?: never;
};

type ModelSource<Limits> = { [Key in keyof Limits]?: never } & {
  model: NumericModel;
  value?: never;
  onChange?: never;
  clearable?: never;
};

/** A number control takes `value` and `onChange` with its limits, or a `model`, never both. */
export type NumberProps<Clearable extends boolean = false> =
  | ValueSource<NumberLimits, Clearable>
  | ModelSource<NumberLimits>;

/** A number control with a slider. It needs `min` and `max`, or a model that has them. */
export type RangeProps<Clearable extends boolean = false> =
  | ValueSource<RangeLimits, Clearable>
  | ModelSource<RangeLimits>;

/** A slider has no text to clear. */
export type SliderProps = ValueSource<RangeLimits, false> | ModelSource<RangeLimits>;

/** How a number shows as text. The step sets the decimals, and the limits set the width. */
export interface NumberFormat {
  /** Shows exactly this many decimals, when the step does not give the precision you need. */
  decimals?: number;
  /** Stored units for each shown unit, such as 1000 to show µm as mm. */
  displayScale?: number;
}

type InputAttributes = Omit<
  HTMLInputAttributes,
  'type' | 'value' | 'disabled' | 'class' | 'size' | 'min' | 'max' | 'step' | `on${string}` | `bind:${string}`
>;

/** The props of the number text, with no box. */
export interface InputProps extends NumberFormat, InputAttributes {
  /** `null`: right in a box with a prefix or a suffix, else left. */
  align?: 'left' | 'right' | null;
  disabled?: boolean;
  /** The text input. */
  ref?: HTMLInputElement | null;
  class?: string;
}

/** The props of a number in the box. */
export interface BoxProps extends InputProps {
  /** The name of the field, at the left in the box. Drag it to change the value. */
  prefix?: string;
  /** Text after the number, such as a unit. */
  suffix?: string;
  size?: 'sm' | 'lg';
  variant?: 'filled' | 'plain';
  /** Lays the number and the parts at its end on 2 columns of the parent grid, so boxes in a stack line up. */
  subgrid?: boolean;
}

interface PageSource extends NumberLimits {
  value?: number | null;
  onChange?(value: number | null, edit: EditContext): unknown;
  clearable?: boolean;
  disabled?: boolean;
}

/** How long a box keeps a saved value while the page shows the old one, for example until a server event. */
const SETTLE_MS = 1000;

/**
 * A number that a page gives with `value` and `onChange`. No value is `NaN`, and the box shows it empty. After a
 * change, the box shows the page's value again: at once if the change fails, and after a short wait if the page
 * does not take the value.
 */
export class PageNumber extends NumericModel {
  readonly #source: () => PageSource;
  #timer: ReturnType<typeof setTimeout> | undefined;
  #reported: string | undefined;

  constructor(source: () => PageSource) {
    const { value, min, max, step, bigStep, home } = source();
    super(value ?? NaN, {
      min,
      max,
      step,
      bigStep,
      home,
      disabled: () => source().disabled ?? false,
      onEditStart: () => source().onEditStart?.() ?? (() => {})
    });
    this.#source = source;
  }

  get clearable(): boolean {
    return this.#source().clearable ?? false;
  }

  /** Takes the page's value and limits. While you edit, the box keeps your value. */
  sync({ value, min, max, step, bigStep, home }: PageSource): void {
    this.update({ kind: 'float', value: value ?? NaN, minimum: min, maximum: max, step });
    this.bigStep = bigStep ?? null;
    this.home = home ?? null;
  }

  /** Sends `null` when the box is clearable. */
  clear(): void {
    if (this.clearable) this.patch(NaN);
  }

  patch(value: number, opts?: { throttled?: boolean }): void {
    // An empty box that stays empty sends nothing, for example while you drag its prefix.
    if (Number.isNaN(value) && Number.isNaN(this.value)) return;
    clearTimeout(this.#timer);
    super.patch(value, opts);
  }

  dispose(): void {
    clearTimeout(this.#timer);
    super.dispose();
  }

  protected publish(value: number, edit: EditContext = {}): void {
    if (this.disabled) return;
    void this.#settle(this.#source().onChange?.(Number.isNaN(value) ? null : value, edit), edit);
  }

  async #settle(result: unknown, edit: EditContext): Promise<void> {
    clearTimeout(this.#timer);
    try {
      await result;
      this.#timer = setTimeout(() => this.#revert(), SETTLE_MS);
    } catch (error) {
      // A drag sends many changes. Report its failure 1 time.
      if (!edit.editId || edit.editId !== this.#reported) reportFailure(error);
      this.#reported = edit.editId;
      this.#revert();
    }
  }

  /** Shows the page's value, also during an edit. */
  #revert(): void {
    this.value = this.#source().value ?? NaN;
  }
}

/**
 * The model of a number control: its `model`, or a PageNumber for `value` and `onChange`. A control gives its model
 * to the parts that it uses, so they all show and change 1 value. Call it while a control starts; it decides between
 * `value` and `model` then.
 */
export function useNumberModel(props: () => PageSource & { model?: NumericModel }): NumericModel {
  const { model } = props();
  if (model) return model;
  const page = new PageNumber(props);
  $effect(() => {
    const { value, min, max, step, bigStep, home } = props();
    untrack(() => page.sync({ value, min, max, step, bigStep, home }));
  });
  onDestroy(() => page.dispose());
  return page;
}

/** The value 1 step away. From no value, the first step goes to the minimum, or down to the maximum. */
export function stepNumber(model: NumericModel, direction: 1 | -1, big = false): number {
  if (Number.isNaN(model.value)) return direction > 0 ? (model.min ?? 0) : (model.max ?? 0);
  return model.value + direction * (big ? model.bigStep : (model.step ?? 1));
}

/** Alt+scroll calls `step` with 1 or -1. */
export function altScroll(step: (direction: 1 | -1) => void): Attachment<HTMLElement> {
  return (node) => {
    const onWheel = (event: WheelEvent) => {
      if (!event.altKey) return;
      event.preventDefault();
      step(event.deltaY < 0 ? 1 : -1);
    };
    node.addEventListener('wheel', onWheel, { passive: false });
    return () => node.removeEventListener('wheel', onWheel);
  };
}

/** With no step and no decimals, a number shows at most this many significant digits. */
const MAX_DIGITS = 6;
/** The width of a number with no limits, in characters. */
const DEFAULT_WIDTH = 8;

/**
 * How a box shows the numbers of its model: its width in characters, and the text of a value ('' for no value). The
 * step sets the most decimals, and the limits at those decimals set the width, so the box keeps its size while the
 * value changes. A value with more decimals than the step, such as one that a device sets, shows them, as many as fit.
 * With no step, the text has up to 6 significant digits, with as many decimals as fit. Only `decimals` keeps trailing
 * zeros.
 */
export function numberDisplay(
  { step, min, max }: Pick<NumericModel, 'step' | 'min' | 'max'>,
  { decimals, displayScale = 1 }: NumberFormat
): { width: number; text: (value: number) => string } {
  const stepPlaces = step == null || !(step > 0) ? undefined : decimalsOf(step / displayScale);
  const width = limitsWidth(min, max, decimals ?? stepPlaces, displayScale);
  return {
    width,
    text(value) {
      if (Number.isNaN(value)) return '';
      const shown = value / displayScale;
      if (!Number.isFinite(shown)) return String(shown);
      if (decimals !== undefined) return shown.toFixed(decimals);
      if (stepPlaces === undefined) return fitDigits(shown, width);
      // The box keeps 1 spare character, so the text can use width + 1 characters.
      const room = width - wholeLength(shown);
      return trimZeros(shown.toFixed(Math.min(decimalsOf(shown), Math.max(stepPlaces, room))));
    }
  };
}

/** The characters of the longest text between the limits. With no step, it keeps room for decimals. */
function limitsWidth(min: number | null, max: number | null, places: number | undefined, displayScale: number): number {
  if (min == null || max == null) return DEFAULT_WIDTH;
  const length = (limit: number) =>
    places === undefined ? wholeLength(limit / displayScale) : (limit / displayScale).toFixed(places).length;
  const width = Math.max(length(min), length(max));
  return places === undefined ? Math.max(width, DEFAULT_WIDTH) : width;
}

/** The characters of the whole part of a number, with its sign. */
function wholeLength(value: number): number {
  return Math.trunc(Math.abs(value)).toString().length + (value < 0 ? 1 : 0);
}

/** Up to 6 significant digits, with as many decimals as fit in the width. */
function fitDigits(shown: number, width: number): string {
  const magnitude = shown === 0 ? 0 : Math.floor(Math.log10(Math.abs(shown)));
  return trimZeros(shown.toFixed(Math.max(0, Math.min(MAX_DIGITS - 1 - magnitude, width - wholeLength(shown) - 1))));
}

/** Drops trailing zeros after the point, and the point if nothing is left after it: `12.50` becomes `12.5`. */
function trimZeros(text: string): string {
  const trimmed = text.replace(/(\.\d*?)0+$/, '$1').replace(/\.$/, '');
  return trimmed === '-0' ? '0' : trimmed;
}

/** Where the value sits between the limits, from 0 to 1. No value, or no limits, gives `null`. */
export function rangeFraction({ value, min, max }: NumericModel): number | null {
  if (Number.isNaN(value) || min == null || max == null || max <= min) return null;
  return Math.min(1, Math.max(0, (value - min) / (max - min)));
}
