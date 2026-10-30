import type { Bounds } from './geometry';

export type RegionField = keyof Bounds;

export class RegionSelection {
  minX = $state<number | null>(null);
  minY = $state<number | null>(null);
  maxX = $state<number | null>(null);
  maxY = $state<number | null>(null);
  #scope: string | null = null;

  get bounds(): Bounds | null {
    const { minX, minY, maxX, maxY } = this;
    return minX !== null && minY !== null && maxX !== null && maxY !== null && maxX > minX && maxY > minY
      ? { minX, minY, maxX, maxY }
      : null;
  }

  setBounds(bounds: Bounds | null): void {
    this.minX = bounds?.minX ?? null;
    this.minY = bounds?.minY ?? null;
    this.maxX = bounds?.maxX ?? null;
    this.maxY = bounds?.maxY ?? null;
  }

  clear(): void {
    this.setBounds(null);
  }

  setScope(scope: string | null): void {
    if (scope === this.#scope) return;
    this.#scope = scope;
    this.clear();
  }
}
