import { ElementSize } from 'runed';

export interface PaneSizeBounds {
  /** Minimum width in px. */
  min?: number;
  /** Maximum width in px. */
  max?: number;
  /** Fallback `minSize` % used before the container is measured. */
  fallbackMin?: number;
  /** Fallback `maxSize` % used before the container is measured. */
  fallbackMax?: number;
}

/**
 * Reactive pixel-based pane sizing for paneforge. Tracks the container width and converts px bounds to
 * the percentages a `<Pane>` expects, exposed under the pane's own prop names so the result spreads
 * straight on: `<Pane defaultSize={16} {...createPaneSize(() => el, { min: 275, max: 325 })} />`.
 */
export function createPaneSize(containerEl: () => HTMLElement | null, bounds: PaneSizeBounds) {
  const size = new ElementSize(containerEl);
  const pct = (px: number, fallback: number) => (size.width > 0 ? (px / size.width) * 100 : fallback);
  return {
    get minSize(): number | undefined {
      return bounds.min !== undefined ? pct(bounds.min, bounds.fallbackMin ?? 25) : undefined;
    },
    get maxSize(): number | undefined {
      return bounds.max !== undefined ? pct(bounds.max, bounds.fallbackMax ?? 100) : undefined;
    }
  };
}
