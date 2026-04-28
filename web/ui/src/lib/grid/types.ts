/** Ephemeral 2D tile position used by the grid view. */
export interface Tile {
  tile_id: string;
  row: number;
  col: number;
  x: number;
  y: number;
  w: number;
  h: number;
}

/** Layer toggles for the stage canvas. */
export interface LayerVisibility {
  grid: boolean;
  stacks: boolean;
  path: boolean;
  fov: boolean;
  thumbnail: boolean;
}
