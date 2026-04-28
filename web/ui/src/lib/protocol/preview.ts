/**
 * Wire schemas for the `preview.*` topic namespace.
 *
 * Frame and tile binaries (`preview.frame.{channel}`, `preview.tile.{channel}`)
 * are NOT typed events — they're a high-throughput binary stream owned by
 * `$lib/preview/`. Same envelope, body is the raw msgpack frame payload.
 */

// Mirrors backend `vxl.camera.preview.PreviewViewport`. Inline to avoid reaching
// into `$lib/app/client.svelte` from a protocol file.
export interface PreviewViewport {
  x: number;
  y: number;
  w: number;
  h: number;
}

// Mirrors backend `vxl.camera.preview.PreviewLevels`. Normalized [0, 1].
export interface PreviewLevels {
  min: number;
  max: number;
}

/** Per-channel preview display config — viewport + levels + colormap. Embedded in `SessionStateUpdate.preview`. */
export interface PreviewConfig {
  viewport: PreviewViewport;
  levels: PreviewLevels;
  colormap: string | null;
}

// ==================== Body shapes (used for both inbound and outbound) ====================
//
// `preview.viewport.set` and `preview.viewport.changed` both carry a bare
// `PreviewViewport`. The per-channel topics bundle channel + payload.

export interface PreviewLevelsUpdate {
  channel: string;
  levels: PreviewLevels;
}

export interface PreviewColormapUpdate {
  channel: string;
  colormap: string;
}

// ==================== Events ====================

export interface PreviewEvents {
  'preview.viewport.changed': PreviewViewport;
  'preview.levels.changed': PreviewLevelsUpdate;
  'preview.colormap.changed': PreviewColormapUpdate;
}

// ==================== Commands ====================
//
// `preview.start`, `preview.stop`, `preview.pause`, `preview.resume` carry no
// body — typed against the shared `Empty` from `./index`.

export interface PreviewCommands {
  'preview.viewport.set': PreviewViewport;
  'preview.levels.set': PreviewLevelsUpdate;
  'preview.colormap.set': PreviewColormapUpdate;
}
