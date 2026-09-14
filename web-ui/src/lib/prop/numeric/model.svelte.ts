import { onDestroy } from 'svelte';

import { type EditContext, NumericModel } from '$lib/model';

export interface RawNumeric {
  value?: number;
  onChange?: (value: number, context: EditContext) => void;
  onEditStart?: () => () => void;
  disabled?: boolean;
  throttleMs?: number;
  min?: number | null;
  max?: number | null;
  step?: number;
  bigStep?: number;
  home?: number | (() => number);
}

/** A numeric control's binding: a shared NumericModel, or raw value/bounds with an onChange. */
export type NumericSource = NumericModel | RawNumeric;

/**
 * Resolve a `NumericSource` into a NumericModel: pass a model through, or build a local one kept in
 * sync from raw props — value/bounds flow in, edits flow out via `onChange`. Call during init.
 */
export function useNumericModel(source: () => NumericSource): NumericModel {
  const initial = source();
  if (initial instanceof NumericModel) return initial;

  const raw = () => source() as RawNumeric;
  const r0 = raw();
  const local = new NumericModel(r0.value ?? 0, {
    min: r0.min,
    max: r0.max,
    step: r0.step,
    bigStep: r0.bigStep,
    home: r0.home,
    throttleMs: r0.throttleMs,
    onEditStart: () => raw().onEditStart?.() ?? (() => {}),
    disabled: () => raw().disabled ?? false,
    onPatch: (v, context) => raw().onChange?.(v, context)
  });
  onDestroy(() => local.dispose());

  // update() is an authoritative sync (no publish), so pulling props in never re-fires onChange.
  $effect(() => {
    const r = raw();
    local.update({ kind: 'float', value: r.value ?? local.value, minimum: r.min, maximum: r.max, step: r.step });
    local.bigStep = r.bigStep ?? null;
    local.home = r.home ?? null;
    local.throttleMs = r.throttleMs ?? 100;
  });

  return local;
}
