import { ElementSize } from 'runed';

export interface PaneSizeBounds {
  /** Minimum extent in px, along the group's direction (width if horizontal, height if vertical). */
  min?: number;
  /** Maximum extent in px, along the group's direction. */
  max?: number;
  /** Default (initial) extent in px, along the group's direction. */
  default?: number;
  /** Percentages to use before the container is measured. */
  fallback?: { min?: number; max?: number; default?: number };
}

/**
 * Reactive pixel-based pane sizing for paneforge. Converts px bounds to the percentages a `<Pane>`
 * expects, measuring the axis that matches the group's `data-direction` (width for horizontal groups,
 * height for vertical). Spread the whole result onto the pane:
 * `<Pane {...createPaneSize(() => el, { default: 280, min: 250, max: 320 })} />`.
 *
 * `defaultSize` is only present when `default` is set, so the spread never clobbers a literal default
 * on panes that don't use one.
 */
export function createPaneSize(containerEl: () => HTMLElement | null, bounds: PaneSizeBounds) {
  const size = new ElementSize(containerEl);
  // Extent along the group's main axis. `ElementSize` is 0 until its ResizeObserver first fires (after
  // mount), so fall back to a synchronous measure — needed for `defaultSize`, which paneforge reads once
  // at mount, before that first observation lands.
  const extent = (): number => {
    const el = containerEl();
    if (!el) return 0;
    const vertical = el.closest('[data-pane-group]')?.getAttribute('data-direction') === 'vertical';
    const live = vertical ? size.height : size.width;
    if (live > 0) return live;
    const rect = el.getBoundingClientRect();
    return vertical ? rect.height : rect.width;
  };
  const pct = (px: number, fallback: number) => {
    const ext = extent();
    return ext > 0 ? (px / ext) * 100 : fallback;
  };

  const result: { minSize?: number; maxSize?: number; defaultSize?: number } = {
    get minSize() {
      return bounds.min !== undefined ? pct(bounds.min, bounds.fallback?.min ?? 25) : undefined;
    },
    get maxSize() {
      return bounds.max !== undefined ? pct(bounds.max, bounds.fallback?.max ?? 100) : undefined;
    }
  };
  if (bounds.default !== undefined) {
    const value = bounds.default;
    Object.defineProperty(result, 'defaultSize', {
      enumerable: true,
      get: () => pct(value, bounds.fallback?.default ?? 30)
    });
  }
  return result;
}
