export { default as PreviewCanvas } from './PreviewCanvas.svelte';
export { default as PreviewInfo } from './PreviewInfo.svelte';
export { default as ColormapPicker } from './ColormapPicker.svelte';
export { default as PanZoomControls } from './PanZoomControls.svelte';
export { default as Histogram } from './Histogram.svelte';
export { default as ChannelHistogram } from './ChannelHistogram.svelte';

export {
  PreviewManager,
  PreviewChannel,
  fetchColormapCatalog,
  isViewportEqual,
  isDefaultViewport,
  channelBoundingBox,
  compositeTiledFrames,
  compositeFullFrames,
  DEFAULT_VIEWPORT
} from './preview.svelte';
export type { ColormapDef, ColormapGroup, ColormapCatalog } from './preview.svelte';

export { SnapshotStore } from './snapshots.svelte';
export type { Snapshot, SnapshotChannel } from './snapshots.svelte';

export { decodeFrameBody, decodeTileBody, channelFromTopic } from './frame';
export type {
  PreviewFrameInfo,
  PreviewTileInfo,
  PreviewTile,
  DecodedFrame,
  DecodedTile,
  DecodedTileBatch
} from './frame';

export type { PreviewConfig, PreviewLevels, PreviewViewport } from '$lib/protocol/preview';
