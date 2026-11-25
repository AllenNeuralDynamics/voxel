/** Pane sizes in rem. The window scrolls sideways when narrower than both `min` widths. */
export const LAYOUT = {
  page: { min: 36, startMax: 80 },
  live: { min: 36 },
  dock: { min: 12, start: 17 }
} as const;
