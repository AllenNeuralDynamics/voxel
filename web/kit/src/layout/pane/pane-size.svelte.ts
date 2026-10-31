import type { PaneAPI } from 'paneforge';
import { ElementSize } from 'runed';

import { pref } from '../../utils/pref';

let rootPx = $state(16);

if (typeof document !== 'undefined') {
  const read = () => {
    rootPx = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
  };
  read();
  new MutationObserver(read).observe(document.documentElement, { attributeFilter: ['style'] });
}

/** Extents are in rem, along the group's direction (width if horizontal, height if vertical). */
export interface PaneSizeBounds {
  collapsed?: number;
  min?: number;
  max?: number;
  default?: number;
  /** Percentages to use before the container is measured. */
  fallback?: { collapsed?: number; min?: number; max?: number; default?: number };
  /**
   * Saves the pane's extent in rem, and whether it is collapsed, under this key. Needs `default`. Leave it off one
   * pane in the group: that pane takes the space left.
   */
  persist?: string;
}

export interface PaneSize {
  collapsedSize?: number;
  minSize?: number;
  maxSize?: number;
  defaultSize?: number;
  onResize?: (size: number) => void;
  onCollapse?: () => void;
  onExpand?: () => void;
  /** Collapses the pane, or opens it at its saved extent. Not enumerable, so spreading the result leaves it out. */
  readonly toggle: (pane: PaneAPI) => void;
}

interface SavedPane {
  /** Open extent in rem. */
  size?: number;
  collapsed?: boolean;
}

/**
 * Bounds track the root font size, so panes scale with the density setting. Spread the whole result onto the pane:
 * `<Pane {...createPaneSize(() => el, { default: 21.5, min: 19, max: 24.5 })} />`.
 *
 * `defaultSize` is present only when `default` is set, so the spread never clobbers a literal default.
 *
 * With `persist`, leave `autoSaveId` off the group: paneforge names its saved layouts after these bounds, which
 * change with the container size. paneforge lays the group out again from each `defaultSize` whenever bounds or panes
 * change, so `defaultSize` gives the saved extent.
 */
export function createPaneSize(containerEl: () => HTMLElement | null, bounds: PaneSizeBounds): PaneSize {
  const size = new ElementSize(containerEl);
  // `ElementSize` is 0 until its ResizeObserver first fires after mount, but paneforge reads `defaultSize` once at
  // mount, so measure synchronously until then.
  const extent = (): number => {
    const el = containerEl();
    if (!el) return 0;
    const vertical = el.closest('[data-pane-group]')?.getAttribute('data-direction') === 'vertical';
    const live = vertical ? size.height : size.width;
    if (live > 0) return live;
    const rect = el.getBoundingClientRect();
    return vertical ? rect.height : rect.width;
  };
  const pct = (rem: number, fallback: number) => {
    const ext = extent();
    return ext > 0 ? ((rem * rootPx) / ext) * 100 : fallback;
  };

  const store = bounds.persist ? pref<SavedPane>(`ui:pane:${bounds.persist}`, {}) : undefined;
  // A plain copy, not reactive: if a save during a drag changed `defaultSize`, paneforge would lay the group out
  // again in the middle of the drag.
  let saved: SavedPane = store?.get() ?? {};
  let toggling = false;
  let timer: ReturnType<typeof setTimeout> | undefined;

  const collapsed = () => pct(bounds.collapsed ?? 0, bounds.fallback?.collapsed ?? 0);
  const open = () => {
    const rem = saved.size ?? bounds.default;
    return rem === undefined ? undefined : pct(rem, bounds.fallback?.default ?? 30);
  };

  // Save only what the user does: drag a divider or use arrow keys on it (paneforge marks it `data-active`), or
  // `toggle`. Layouts that paneforge makes by itself, such as panes squeezed into a narrow window, are not saved.
  const byUser = (): boolean => {
    if (toggling) return true;
    const group = containerEl()?.closest('[data-pane-group]');
    const id = group?.getAttribute('data-pane-group-id');
    return Boolean(
      id && group?.querySelector(`[data-pane-resizer][data-active][data-pane-group-id="${CSS.escape(id)}"]`)
    );
  };
  const save = (next: SavedPane) => {
    saved = next;
    clearTimeout(timer);
    timer = setTimeout(() => store?.set(saved), 100);
  };

  const result: Omit<PaneSize, 'toggle'> = {
    get collapsedSize() {
      return bounds.collapsed !== undefined ? collapsed() : undefined;
    },
    get minSize() {
      return bounds.min !== undefined ? pct(bounds.min, bounds.fallback?.min ?? 25) : undefined;
    },
    get maxSize() {
      return bounds.max !== undefined ? pct(bounds.max, bounds.fallback?.max ?? 100) : undefined;
    }
  };
  if (bounds.default !== undefined) {
    Object.defineProperty(result, 'defaultSize', {
      enumerable: true,
      get: () => (saved.collapsed && bounds.collapsed !== undefined ? collapsed() : open())
    });
  }
  if (store) {
    result.onResize = (percent) => {
      const ext = extent();
      if (!byUser() || ext === 0 || (bounds.collapsed !== undefined && percent <= collapsed())) return;
      save({ ...saved, size: ((percent / 100) * ext) / rootPx });
    };
    result.onCollapse = () => {
      if (byUser()) save({ ...saved, collapsed: true });
    };
    result.onExpand = () => {
      if (byUser()) save({ ...saved, collapsed: false });
    };
  }
  Object.defineProperty(result, 'toggle', {
    value: (pane: PaneAPI) => {
      toggling = true;
      try {
        const size = open();
        if (!pane.isCollapsed()) pane.collapse();
        else if (size === undefined) pane.expand();
        else pane.resize(size);
      } finally {
        toggling = false;
      }
    }
  });
  return result as PaneSize;
}
