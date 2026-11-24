/**
 * Sizes of the station window's parts, in rem. The page starts at most `page.startMax` wide; the page and the live
 * profile each keep their `min` while the divider between them is dragged, and the window scrolls sideways when it
 * is narrower than both together. A dock panel (Diagnostics under the page, Stream and Power under the live
 * image) opens at `dock.start` and keeps at least `dock.min`; what is above it keeps half the column.
 */
export const LAYOUT = {
  page: { min: 36, startMax: 80 },
  live: { min: 36 },
  dock: { min: 12, start: 17 }
} as const;
