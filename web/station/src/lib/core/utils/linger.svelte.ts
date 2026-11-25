/**
 * A value that stays `ms` after its source turns null, so a brief value does not flash. Create during component init.
 */
export class Linger<T> {
  #current = $state<T | null>(null);

  constructor(source: () => T | null, ms: number) {
    // Rerun only on a new value; an equal value must not restart the timer.
    const now = $derived(source());
    $effect(() => {
      const value = now;
      if (value !== null) {
        this.#current = value;
        return;
      }
      const timer = setTimeout(() => (this.#current = null), ms);
      return () => clearTimeout(timer);
    });
  }

  get current(): T | null {
    return this.#current;
  }
}
