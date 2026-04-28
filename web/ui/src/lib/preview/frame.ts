/**
 * Frame body shapes + decoder.
 *
 * Preview frames arrive on the bus as raw bytes on per-channel topics
 * (`preview.frame.{channel}`, `preview.tile.{channel}`). Each body is
 * msgpack-encoded by the backend camera path; this module unpacks it and
 * produces ready-to-render `ImageBitmap`s.
 *
 * Wire shape lives here (not in `$lib/protocol/`) because frames are a
 * binary domain stream, not a typed event registered with the bus.
 */

import { unpack } from 'msgpackr';

import type { PreviewLevels, PreviewViewport } from '$lib/protocol/preview';

// ── Wire body shapes ────────────────────────────────────────────────

export interface PreviewFrameInfo {
  frame_idx: number;
  width: number;
  height: number;
  full_width: number;
  full_height: number;
  levels: PreviewLevels;
  fmt: 'jpeg' | 'png' | 'uint16';
  histogram?: number[];
  colormap?: string;
}

export interface PreviewTileInfo {
  frame_idx: number;
  width: number;
  height: number;
  full_width: number;
  full_height: number;
  levels: PreviewLevels;
  fmt: 'jpeg' | 'png' | 'uint16';
  colormap?: string;
  scale: number;
  viewport: PreviewViewport;
}

export interface PreviewTile {
  col: number;
  row: number;
  width: number;
  height: number;
  data: ArrayBuffer;
}

// ── Decoded outputs (what the subscriber receives) ──────────────────

export interface DecodedFrame {
  info: PreviewFrameInfo;
  bitmap: ImageBitmap;
}

export interface DecodedTile {
  col: number;
  row: number;
  width: number;
  height: number;
  bitmap: ImageBitmap;
}

export interface DecodedTileBatch {
  info: PreviewTileInfo;
  tiles: DecodedTile[];
}

// ── Decoders ────────────────────────────────────────────────────────

export async function decodeFrameBody(body: Uint8Array): Promise<DecodedFrame | null> {
  const frame = unpack(body) as { info: PreviewFrameInfo; data: ArrayBuffer };
  if (!frame.info || !frame.data) return null;
  const bitmap = await decodeBitmap(frame.info.fmt, frame.data);
  return bitmap ? { info: frame.info, bitmap } : null;
}

export async function decodeTileBody(body: Uint8Array): Promise<DecodedTileBatch | null> {
  const batch = unpack(body) as { info: PreviewTileInfo; tiles: PreviewTile[] };
  if (!batch.info || !batch.tiles) return null;

  const decoded = await Promise.all(
    batch.tiles.map(async (tile) => {
      const bitmap = await decodeBitmap(batch.info.fmt, tile.data);
      return bitmap ? { col: tile.col, row: tile.row, width: tile.width, height: tile.height, bitmap } : null;
    })
  );

  const tiles = decoded.filter((t): t is DecodedTile => t !== null);
  return tiles.length > 0 ? { info: batch.info, tiles } : null;
}

/** Channel id is encoded in the topic suffix: `preview.frame.{channel}` / `preview.tile.{channel}`. */
export function channelFromTopic(topic: string, prefix: 'preview.frame' | 'preview.tile'): string {
  return topic.slice(prefix.length + 1);
}

// ── Internal ────────────────────────────────────────────────────────

async function decodeBitmap(fmt: 'jpeg' | 'png' | 'uint16', data: ArrayBuffer): Promise<ImageBitmap | null> {
  let mimeType: string;
  switch (fmt) {
    case 'jpeg':
      mimeType = 'image/jpeg';
      break;
    case 'png':
      mimeType = 'image/png';
      break;
    case 'uint16':
      console.warn('[preview/frame] uint16 format not yet supported');
      return null;
    default:
      console.warn('[preview/frame] Unknown frame format:', fmt);
      return null;
  }
  const blob = new Blob([data], { type: mimeType });
  return await createImageBitmap(blob, { colorSpaceConversion: 'none' });
}
