/**
 * Compares 2 values that are data: text, numbers, true and false, null, and lists and maps of these, however deep. A
 * list is compared item by item, by place. A value that is missing counts as null.
 */
export class ObjectDiff {
  /** The items of a list or a map by key, or undefined for a plain value. */
  static parts(value: unknown): Record<string, unknown> | undefined {
    return value !== null && typeof value === 'object' ? (value as Record<string, unknown>) : undefined;
  }

  /** The keys of `now`, then the keys that only `was` has. Empty when neither is a list or a map. */
  static keys(now: unknown, was: unknown): string[] {
    return [...new Set([...Object.keys(ObjectDiff.parts(now) ?? {}), ...Object.keys(ObjectDiff.parts(was) ?? {})])];
  }

  /**
   * How many plain values of `now` are not the values of `was`. A list or a map against a plain value, or against
   * one with nothing in it, is at least 1.
   */
  static count(now: unknown, was: unknown): number {
    const [a, b] = [ObjectDiff.parts(now), ObjectDiff.parts(was)];
    if (!a && !b) return (now ?? null) === (was ?? null) ? 0 : 1;
    const inside = ObjectDiff.keys(now, was).reduce((sum, key) => sum + ObjectDiff.count(a?.[key], b?.[key]), 0);
    return a && b ? inside : Math.max(1, inside);
  }

  /** Whether `now` and `was` hold the same values. */
  static same(now: unknown, was: unknown): boolean {
    return ObjectDiff.count(now, was) === 0;
  }
}
