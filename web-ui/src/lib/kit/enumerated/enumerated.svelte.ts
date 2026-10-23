import type { EnumeratedModel } from '$lib/core/model/prop.svelte';

import { useValue } from '../value.svelte';

/**
 * Select and RadioBar take `value`, `options` and `onChange`, or an `EnumeratedModel`, never both.
 * With no value, no option is picked, for example while the device does not know its position.
 */
export type EnumeratedProps<T extends string | number> =
  | { value: T | null | undefined; options: readonly T[]; onChange: (value: T) => unknown; model?: never }
  | { model: EnumeratedModel<T>; value?: never; options?: never; onChange?: never };

interface Source<T extends string | number> {
  value?: T | null;
  options?: readonly T[];
  onChange?: (value: T) => unknown;
  model?: EnumeratedModel<T>;
  disabled?: boolean;
}

/** The key of an option for the bits-ui parts, which only know text. No value has the empty key. */
export function optionKey(option: string | number | null | undefined): string {
  return option == null ? '' : String(option);
}

/** What Select and RadioBar show, and how they pick. Picking the option that shows does nothing. */
export function useEnumerated<T extends string | number>(props: () => Source<T>) {
  const control = useValue<T, T | null | undefined>(props);
  const options = $derived.by(() => {
    const { model, options = [] } = props();
    return model ? model.options : options;
  });

  return {
    get value(): T | null {
      return control.value ?? null;
    },
    get options(): readonly T[] {
      return options;
    },
    get disabled(): boolean {
      return control.disabled;
    },
    get pending(): boolean {
      return control.pending;
    },
    pick(key: string): void {
      const next = options.find((option) => optionKey(option) === key);
      if (next !== undefined && next !== control.value) void control.change(next);
    }
  };
}
