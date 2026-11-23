/**
 * A value that shows at once and stays `ms` after its source turns null, so a value that is there only for a moment
 * does not flash. A new value during that time shows at once. Make it while a component initializes; its timer stops
 * with the component.
 */
export class Linger<T> {
  #current = $state<T | null>(null);

  constructor(source: () => T | null, ms: number) {
    $effect(() => {
      const value = source();
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
