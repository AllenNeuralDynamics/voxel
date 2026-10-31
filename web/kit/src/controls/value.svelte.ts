import { onDestroy } from 'svelte';

import { reportFailure } from '../failures';
import type { BasePropModel } from './models.svelte';

/**
 * How long a control keeps a saved value while the page still shows the old one, for example until a device
 * reports it.
 */
const SETTLE_MS = 1000;

export type ValueProps<T, Model extends BasePropModel<T>> =
  | { value: T; onChange: (value: T) => unknown; model?: never }
  | { model: Model; value?: never; onChange?: never };

interface Source<T, Shown> {
  value?: Shown;
  onChange?: (value: T) => unknown;
  model?: BasePropModel<T>;
  disabled?: boolean;
}

/**
 * `Shown` is wider than `T` when a control can show no value, such as a choice that the device does not know yet.
 * After a change, the control keeps the new value until the value it gets changes, or for `SETTLE_MS`, so it does not
 * flip back while a device reports the change. Create it while the component starts.
 */
export function useValue<T, Shown = T>(
  props: () => Source<T, Shown>,
  onFailure: (error: unknown) => void = reportFailure
) {
  const source = $derived.by(() => {
    const { value, onChange, model, disabled = false } = props();
    return model
      ? { value: model.value as T | Shown, save: (next: T) => model.patch(next), disabled: disabled || model.disabled }
      : { value: value as T | Shown, save: onChange, disabled };
  });
  let pending = $state<{ value: T } | null>(null);
  let saved = $state<{ value: T; replaced: T | Shown } | null>(null);
  let timer: ReturnType<typeof setTimeout> | undefined;
  onDestroy(() => clearTimeout(timer));

  return {
    get value(): T | Shown {
      if (pending) return pending.value;
      return saved && Object.is(source.value, saved.replaced) ? saved.value : source.value;
    },
    get disabled(): boolean {
      return source.disabled;
    },
    get pending(): boolean {
      return pending !== null;
    },
    async change(next: T): Promise<void> {
      if (pending || source.disabled) return;
      const replaced = source.value;
      pending = { value: next };
      try {
        await source.save?.(next);
        clearTimeout(timer);
        saved = { value: next, replaced };
        timer = setTimeout(() => (saved = null), SETTLE_MS);
      } catch (error) {
        onFailure(error);
      } finally {
        pending = null;
      }
    }
  };
}
