import { ElementSize } from 'runed';

/**
 * Creates a reactive pane min-size calculator that converts a pixel minimum
 * to a percentage of the container width (as required by paneforge).
 *
 * @param containerEl - Getter for the PaneGroup element ref
 * @param minPx - Minimum width in pixels
 * @param fallback - Fallback percentage when container hasn't been measured yet
 */
export function createPaneMinSize(containerEl: () => HTMLElement | null, minPx: number, fallback = 25) {
  const size = new ElementSize(containerEl);
  return {
    get value() {
      return size.width > 0 ? (minPx / size.width) * 100 : fallback;
    }
  };
}
